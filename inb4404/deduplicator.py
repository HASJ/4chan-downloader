"""Deduplication logic for removing duplicate files."""
import os
import logging
from typing import Dict, List

from .config import Config
from .database import HashDB
from .file_utils import FileManager

log = logging.getLogger('inb4404')


class Deduplicator:
    """Scans downloads directory and removes duplicate files."""

    def __init__(self, config: Config, workpath: str):
        """Initialize the Deduplicator.

        Args:
            config: Configuration settings.
            workpath: Base working directory path.
        """
        self.config = config
        self.workpath = workpath
        db_path = os.path.join(workpath, 'hashes.db')
        self.db = HashDB(db_path=db_path)
        self.file_manager = FileManager()
        self.downloads_root = os.path.join(workpath, 'downloads')

    def scan_directory(self) -> Dict[str, List[str]]:
        """Scan the downloads directory and collect files by MD5 hash.

        Returns:
            A dictionary mapping MD5 hashes to lists of file paths.
        """
        md5_map: Dict[str, List[str]] = {}

        if not os.path.exists(self.downloads_root):
            log.warning(f'No downloads directory found at {self.downloads_root}')
            return md5_map

        if self.config.verbose:
            log.info(f'Scanning files in downloads directory: {self.downloads_root}')

        # Collect files and their MD5s
        for root, dirs, files in os.walk(self.downloads_root):
            for fn in files:
                if fn == '.hashes.txt':
                    continue
                full = os.path.join(root, fn)
                if not os.path.isfile(full):
                    continue
                h = self.file_manager.compute_hash(full)
                if not h:
                    log.warning(f'Could not read file for hashing: {full}')
                    continue
                md5_map.setdefault(h, []).append(full)
                if self.config.verbose:
                    log.info(f'Hashed: {full} -> {h}')

        if self.config.verbose:
            total_files = sum(len(v) for v in md5_map.values())
            log.info(f'Found {total_files} files, {len(md5_map)} unique hashes')

        return md5_map

    def find_duplicates(self, md5_map: Dict[str, List[str]]) -> Dict[str, tuple]:
        """Find duplicate files, keeping the oldest for each hash.

        Args:
            md5_map: Dictionary mapping MD5 hashes to lists of file paths.

        Returns:
            A dictionary mapping MD5 hashes to (kept_path, duplicate_paths) tuples.
        """
        duplicates = {}
        for h, paths in md5_map.items():
            if len(paths) <= 1:
                continue  # No duplicates
            # Sort by mtime ascending (oldest first)
            paths_sorted = sorted(paths, key=lambda p: os.path.getmtime(p))
            kept = paths_sorted[0]
            duplicate_paths = paths_sorted[1:]
            duplicates[h] = (kept, duplicate_paths)
        return duplicates

    def remove_duplicates(self, md5_map: Dict[str, List[str]]) -> tuple:
        """Remove duplicate files, keeping the oldest for each hash.

        Args:
            md5_map: Dictionary mapping MD5 hashes to lists of file paths.

        Returns:
            A tuple of (kept_count, deleted_count).
        """
        kept_count = 0
        deleted_count = 0

        for h, paths in md5_map.items():
            # Sort by mtime ascending (oldest first)
            paths_sorted = sorted(paths, key=lambda p: os.path.getmtime(p))
            kept = paths_sorted[0]
            duplicates = paths_sorted[1:]

            if duplicates:
                kept_count += 1
                # Determine thread name relative to downloads root
                rel = os.path.relpath(kept, self.downloads_root)
                thread_name = os.path.dirname(rel).replace(os.sep, '/')
                # Ensure DB points to the kept path
                self.db.upsert(h, kept, thread_name)

                if self.config.verbose:
                    log.info(f'Hash {h}: keeping {kept}, deleting {len(duplicates)} duplicates')

                for d in duplicates:
                    try:
                        os.remove(d)
                        deleted_count += 1
                        log.info(f'Removed duplicate: {d} (kept {kept})')
                    except Exception as e:
                        log.warning(f'Failed to remove duplicate {d}: {e}')
            else:
                # No duplicates, but ensure DB entry exists
                kept_count += 1
                rel = os.path.relpath(kept, self.downloads_root)
                thread_name = os.path.dirname(rel).replace(os.sep, '/')
                self.db.upsert(h, kept, thread_name)

        return (kept_count, deleted_count)

    def remove_legacy_files(self) -> None:
        """Remove legacy .hashes.txt files."""
        for root, dirs, files in os.walk(self.downloads_root):
            for fn in files:
                if fn == '.hashes.txt':
                    fp = os.path.join(root, fn)
                    try:
                        os.remove(fp)
                        log.info(f'Removed legacy file: {fp}')
                    except Exception as e:
                        log.warning(f'Could not remove legacy .hashes.txt {fp}: {e}')

    def run(self) -> None:
        """Run the deduplication process."""
        # Scan directory
        md5_map = self.scan_directory()

        if not md5_map:
            return

        # Remove duplicates
        kept_count, deleted_count = self.remove_duplicates(md5_map)

        log.info(f'Dedupe complete. Kept {kept_count} groups, removed {deleted_count} files')

        # Remove legacy files
        self.remove_legacy_files()

