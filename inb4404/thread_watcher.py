"""Thread watcher for monitoring and downloading files from threads."""
import os
import re
import time
import base64
import logging
import hashlib
from typing import List, Tuple, Optional, Set, Dict, Any

from .config import Config
from .database import HashDB
from .http_client import HTTPClient
from .file_utils import FileManager
from .thread_parser import ThreadParser, ThreadURL
from .exceptions import ThreadNotFoundError, HTTPError

log = logging.getLogger('inb4404')


class ThreadWatcher:
    """Monitors a thread and downloads new files as they appear."""

    def __init__(self, thread_url: str, config: Config, workpath: str):
        """Initialize the ThreadWatcher.

        Args:
            thread_url: The URL of the thread to watch.
            config: Configuration settings.
            workpath: Base working directory path.
        """
        self.thread_url = thread_url
        self.config = config
        self.workpath = workpath
        self.parser = ThreadParser()
        self.http_client = HTTPClient()
        # Initialize DB with proper path
        db_path = os.path.join(workpath, 'hashes.db')
        self.db = HashDB(db_path=db_path)
        self.file_manager = FileManager()

        # Parse thread URL
        self.thread_info = self.parser.parse_url(thread_url)
        self.board = self.thread_info.board
        self.thread_id = self.thread_info.thread_id

        # Determine directory name
        self.thread_dir_name = self._determine_directory_name()

        # Directory for downloads
        self.directory = os.path.join(workpath, 'downloads', self.board, self.thread_dir_name)
        FileManager.ensure_directory(self.directory)

        # Per-thread hash set
        self.md5_hashes: Set[str] = set()

        # Throttle (can be adjusted on 429)
        self.throttle = config.throttle

        log.info(f'Watching {self.board}/{self.thread_id} (Dir: {self.thread_dir_name})')

    def _determine_directory_name(self) -> str:
        """Determine the directory name to use for this thread.

        Returns:
            The directory name (thread_id, slug, or "ID (Subject)").
        """
        thread_dir_name = self.thread_id

        # Check for existing slug or --use-names flag
        if self.thread_info.slug:
            slug_path = os.path.join(self.workpath, 'downloads', self.board, self.thread_info.slug)
            if self.config.use_names or os.path.exists(slug_path):
                thread_dir_name = self.thread_info.slug

        # Logic for --subject: override directory name with "ID (Subject)"
        if self.config.subject:
            try:
                subject = self.parser.get_subject(self.board, self.thread_id)
                if subject:
                    thread_dir_name = f"{self.thread_id} ({subject})"
                else:
                    if self.config.verbose:
                        log.warning(f'Could not fetch subject for {self.board}/{self.thread_id}, using thread_id as directory name')
            except Exception as e:
                log.warning(f'Error fetching subject for {self.board}/{self.thread_id}: {e}, using thread_id as directory name')

        return thread_dir_name

    def _load_existing_hashes(self) -> None:
        """Load existing hashes from the database."""
        # Initialize DB
        self.db.init()

        if self.config.verbose:
            cnt = self.db.count_hashes()
            log.info(f'Loaded {cnt} global hashes from DB {self.db.db_path}')

        # Load per-thread hashes from DB
        # Use thread_id (not thread_dir_name) for backward compatibility
        self.md5_hashes = self.db.get_thread_hashes(self.thread_id)

        if self.config.verbose:
            log.info(
                f'Loaded {len(self.md5_hashes)} per-thread hashes from DB for '
                f'{self.board}/{self.thread_dir_name}'
            )

    def _scan_directory(self) -> None:
        """Scan the thread directory and integrate existing files into the hash set."""
        if not os.path.exists(self.directory):
            return

        for filename in os.listdir(self.directory):
            full_path = os.path.join(self.directory, filename)
            if not os.path.isfile(full_path):
                continue

            # Remove legacy .hashes.txt files
            if filename == '.hashes.txt':
                try:
                    os.remove(full_path)
                    if self.config.verbose:
                        log.info(f'Removed legacy .hashes.txt in {self.directory}')
                except Exception:
                    pass
                continue

            # Compute hash
            file_hash = self.file_manager.compute_hash(full_path)
            if not file_hash:
                continue

            # Check for duplicates
            gpath = self.db.get_path(file_hash)
            if gpath and os.path.abspath(gpath) != os.path.abspath(full_path) and os.path.exists(gpath):
                try:
                    os.remove(full_path)
                    if self.config.verbose:
                        log.info(f'Removed duplicate file: {full_path} (duplicate of {gpath})')
                    continue
                except OSError as e:
                    log.warning(f'Could not remove duplicate file {full_path}: {e}')
            # If the stored path doesn't exist (file was moved/deleted), update the DB
            elif gpath and not os.path.exists(gpath):
                self.db.upsert(file_hash, full_path, self.thread_id)

            # Add to per-thread set and ensure DB entry
            self.md5_hashes.add(file_hash)
            self.db.insert(file_hash, full_path, self.thread_id)

    def _fetch_thread_data(self) -> Tuple[List[Tuple], List[str]]:
        """Fetch thread data and extract file entries.

        Returns:
            A tuple of (file_entries, titles). file_entries is a list of tuples
            containing file information. titles is a list of extracted titles
            (empty if not using HTML fallback).
        """
        all_titles = []

        # Try JSON API first
        try:
            thread_json = self.http_client.fetch_thread_api(self.board, self.thread_id)
            if thread_json:
                posts = thread_json.get('posts', [])
                file_entries = []
                for p in posts:
                    if 'tim' in p and 'ext' in p and 'md5' in p:
                        tim = p['tim']
                        ext = p['ext']
                        api_md5_b64 = p['md5']
                        api_md5_hex = None
                        try:
                            api_md5_hex = base64.b64decode(api_md5_b64).hex()
                        except Exception:
                            api_md5_hex = None
                        filename = (p.get('filename') or str(tim)) + ext
                        file_url = f'https://i.4cdn.org/{self.board}/{tim}{ext}'
                        file_entries.append((
                            file_url, filename, api_md5_hex, api_md5_b64,
                            p.get('filename'), tim, ext
                        ))
                return (sorted(file_entries, key=lambda t: t[1]), all_titles)
        except Exception:
            pass

        # Fallback to HTML scraping
        try:
            html_result = self.http_client.fetch(self.thread_url).decode('utf-8')
            regex = r'(//i(?:s|)\d*\.(?:4cdn|4chan)\.org/\w+/(\d+\.(?:jpg|png|gif|webm|pdf|mp4)))'
            items = list(set(re.findall(regex, html_result)))
            items = sorted(items, key=lambda tup: tup[1])

            if self.config.title:
                all_titles = self.parser.extract_titles(html_result)

            return (items, all_titles)
        except Exception as e:
            log.warning(f'Failed to fetch thread data: {e}')
            return ([], [])

    def _determine_file_path(
        self,
        enum_tuple: Tuple,
        enum_index: int,
        all_titles: List[str]
    ) -> Optional[str]:
        """Determine the file path for a file entry.

        Args:
            enum_tuple: The file entry tuple.
            enum_index: The index of this entry.
            all_titles: List of extracted titles from HTML.

        Returns:
            The file path, or None if the entry is invalid.
        """
        # Unpack tuple fields
        link = img = api_md5_hex = api_md5_b64 = original_name = tim = ext = None
        if len(enum_tuple) >= 1:
            link = enum_tuple[0]
        if len(enum_tuple) >= 2:
            img = enum_tuple[1]
        if len(enum_tuple) >= 3:
            api_md5_hex = enum_tuple[2]
        if len(enum_tuple) >= 4:
            api_md5_b64 = enum_tuple[3]
        if len(enum_tuple) >= 5:
            original_name = enum_tuple[4]
        if len(enum_tuple) >= 6:
            tim = enum_tuple[5]
        if len(enum_tuple) >= 7:
            ext = enum_tuple[6]

        # Logic for naming the file when --title is used
        if self.config.title:
            imgname = None
            if original_name:
                file_ext = ext if ext else os.path.splitext(img or '')[1]
                imgname = original_name + (file_ext or '')
            elif len(all_titles) > enum_index:
                imgname = all_titles[enum_index]

            if imgname:
                return os.path.join(self.directory, self.file_manager.sanitize_filename(imgname))

        # Default naming logic
        chosen_name = img
        if self.config.origin_name:
            if original_name:
                file_ext = ext if ext else os.path.splitext(img or '')[1]
                chosen_name = original_name + (file_ext or '')
            else:
                base = os.path.basename(img or '')
                stripped = re.sub(r'^[0-9]+(?:[._\-]+)?', '', base)
                if stripped:
                    chosen_name = stripped

        if not chosen_name:
            if img:
                fallback_name = os.path.basename(img)
            elif tim:
                fallback_name = str(tim) + (ext or '')
            else:
                fallback_name = 'file'
            safe_name = fallback_name
        else:
            safe_name = chosen_name

        return os.path.join(self.directory, safe_name)

    def _process_file_entry(
        self,
        enum_tuple: Tuple,
        enum_index: int,
        all_titles: List[str],
        total: int,
        count: int
    ) -> int:
        """Process a single file entry.

        Args:
            enum_tuple: The file entry tuple.
            enum_index: The index of this entry.
            all_titles: List of extracted titles.
            total: Total number of files.
            count: Current count.

        Returns:
            Updated count.
        """
        # Determine file path
        img_path = self._determine_file_path(enum_tuple, enum_index, all_titles)
        if not img_path:
            return count + 1

        # Check if file already exists
        if os.path.exists(img_path):
            return count + 1

        # Unpack for MD5 checking
        link = enum_tuple[0] if len(enum_tuple) >= 1 else None
        img = enum_tuple[1] if len(enum_tuple) >= 2 else None
        api_md5_hex = enum_tuple[2] if len(enum_tuple) >= 3 else None

        # Check API MD5 before downloading
        if api_md5_hex:
            gpath = self.db.get_path(api_md5_hex)
            if gpath:
                if self.config.verbose:
                    log.debug(f'Duplicate (global API md5) skipping {img} (MD5: {api_md5_hex})')
                return count + 1
            if api_md5_hex in self.md5_hashes:
                if self.config.verbose:
                    log.debug(f'Duplicate (thread API md5) skipping {img} (MD5: {api_md5_hex})')
                return count + 1

        # Download the file
        if not link:
            if self.config.verbose:
                log.warning(f'Skipping item with missing link at index {enum_index} in {self.board}/{self.thread_dir_name}')
            return count + 1

        try:
            if self.config.verbose:
                display_save = os.path.basename(img_path) or (img or '')
                log.debug(f'Downloading {display_save} from {self.board}/{self.thread_dir_name} (url: {link})')

            data = self.http_client.fetch(link)
            data_hash = self.file_manager.compute_hash_bytes(data)

            # Double-check after download
            if data_hash in self.md5_hashes or self.db.has_hash(data_hash):
                if self.config.verbose:
                    log.debug(f'Duplicate found after download (MD5: {data_hash}), skipping {img or ""}')
                return count + 1

            # Save the file
            self._save_file(img_path, data, data_hash, total, count)
            count += 1

            # Delay between downloads
            time.sleep(self.throttle)

        except (HTTPError, ThreadNotFoundError) as e:
            log.warning(f'Failed to download {link}: {e}')
        except Exception as e:
            log.warning(f'Unexpected error downloading {link}: {e}')

        return count

    def _save_file(self, img_path: str, data: bytes, data_hash: str, total: int, count: int) -> None:
        """Save a downloaded file to disk.

        Args:
            img_path: Path where to save the file.
            data: File data bytes.
            data_hash: MD5 hash of the file.
            total: Total number of files.
            count: Current count.
        """
        # Write file
        with open(img_path, 'wb') as f:
            f.write(data)

        # Update hashes and DB
        self.md5_hashes.add(data_hash)
        self.db.insert(data_hash, img_path, self.thread_id)

        # Log
        filename_only = os.path.basename(img_path)
        if self.config.with_counter:
            log.info(
                f'[{str(count).rjust(len(str(total)))}/{total}] NEW: '
                f'{self.board}/{self.thread_dir_name} {filename_only}'
            )
        else:
            log.info(f'NEW: {self.board}/{self.thread_dir_name} {filename_only}')

        # Copy to new/ directory if requested
        if self.config.new_dir:
            copy_directory = os.path.join(self.workpath, 'new', self.board, self.thread_dir_name)
            FileManager.ensure_directory(copy_directory)
            name_for_copy = os.path.basename(img_path) or 'file'
            copy_path = os.path.join(copy_directory, name_for_copy)
            with open(copy_path, 'wb') as f:
                f.write(data)

    def watch(self) -> None:
        """Main watch loop - monitors the thread and downloads new files."""
        # Load existing hashes
        self._load_existing_hashes()

        # Scan directory for existing files
        self._scan_directory()

        # Main polling loop
        while True:
            try:
                # Fetch thread data
                items, all_titles = self._fetch_thread_data()
                total = len(items)
                count = 1

                # Process each file entry
                for enum_index, enum_tuple in enumerate(items):
                    count = self._process_file_entry(enum_tuple, enum_index, all_titles, total, count)

            except HTTPError as ex:
                # Handle 429 Too Many Requests
                if hasattr(ex, 'code') and ex.code == 429:
                    log.info(f'{self.thread_url} 429\'d')
                    self.throttle += self.config.backoff
                    sleep_time = 10 + self.throttle
                    time.sleep(sleep_time)
                    continue

                # Try to reload thread
                try:
                    time.sleep(10)
                    self.http_client.fetch(self.thread_url)
                except ThreadNotFoundError:
                    # Thread 404'd - exit with code 404
                    import sys
                    raise SystemExit(404)
                except HTTPError as ex2:
                    code = getattr(ex2, 'code', None)
                    log.info(f'{self.thread_url} {code}\'d')
                    if code == 404:
                        import sys
                        raise SystemExit(404)
                    break
                continue

            except Exception as e:
                log.fatal(f'{self.thread_url} crashed! {e}')
                raise

            # Sleep before next refresh
            time.sleep(self.config.refresh_time)

            if self.config.verbose:
                log.info(f'Checking {self.board}/{self.thread_dir_name}')

