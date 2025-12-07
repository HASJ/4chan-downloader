"""Process manager for multi-thread file watching."""
import os
import time
import logging
from multiprocessing import Process
from typing import Dict, Set, Optional

from .config import Config
from .thread_watcher import ThreadWatcher
from .http_client import HTTPClient
from .exceptions import ThreadNotFoundError

log = logging.getLogger('inb4404')


def _call_watcher(thread_url: str, config: Config, workpath: str) -> None:
    """Helper wrapper used when spawning a multiprocessing.Process.

    The Process target should be a picklable callable; this thin wrapper lets
    the child process run ThreadWatcher.watch() and simply ignores
    KeyboardInterrupt so cleanup can proceed gracefully in the parent.
    Ensure logging is configured in spawned child processes so that
    per-file download messages are emitted to the console when the
    script is run in "file of links" mode (multiprocessing spawn
    on Windows doesn't inherit the parent's basicConfig). Use the
    same date format selection as the main process.

    Args:
        thread_url: The URL of the thread to watch.
        config: Configuration settings.
        workpath: Base working directory path.
    """
    try:
        # Configure logging for child process
        if config.date:
            logging.basicConfig(
                level=logging.INFO,
                format='[%(asctime)s] %(message)s',
                datefmt='%Y-%m-%d %I:%M:%S %p'
            )
        else:
            logging.basicConfig(
                level=logging.INFO,
                format='[%(asctime)s] %(message)s',
                datefmt='%I:%M:%S %p'
            )
    except Exception:
        # If logging config fails for any reason, continue anyway
        pass

    try:
        watcher = ThreadWatcher(thread_url, config, workpath)
        watcher.watch()
    except KeyboardInterrupt:
        pass
    except SystemExit as e:
        # Re-raise SystemExit to preserve exit code (e.g., 404)
        raise


class ProcessManager:
    """Manages multiple watcher processes for threads listed in a file."""

    def __init__(self, filename: str, config: Config, workpath: str):
        """Initialize the ProcessManager.

        Args:
            filename: Path to the file containing thread URLs.
            config: Configuration settings.
            workpath: Base working directory path.
        """
        self.filename = filename
        self.config = config
        self.workpath = workpath
        self.running_processes: Dict[str, Process] = {}
        self.http_client = HTTPClient()

    def load_queue(self) -> Set[str]:
        """Load thread URLs from the queue file.

        Returns:
            A set of valid thread URLs (lines starting with 'http' and not disabled).
        """
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                # A link is valid if it starts with http and not with a '-'
                desired_links = {
                    line.strip() for line in f
                    if line.strip().startswith('http') and not line.strip().startswith('-http')
                }
            return desired_links
        except FileNotFoundError:
            log.error(f'File not found: {self.filename}')
            return set()

    def start_watcher(self, link: str) -> None:
        """Start a watcher process for a thread URL.

        Args:
            link: The thread URL to watch.
        """
        if link in self.running_processes:
            if self.config.verbose:
                log.info(f'Already watching {link}')
            return

        log.info(f'Starting new watcher for {link}')
        process = Process(
            target=_call_watcher,
            args=(link, self.config, self.workpath)
        )
        process.start()
        self.running_processes[link] = process

    def stop_watcher(self, link: str) -> None:
        """Stop a watcher process for a thread URL.

        Args:
            link: The thread URL to stop watching.
        """
        if link not in self.running_processes:
            return

        log.info(f'Link {link} removed from file. Stopping watcher.')
        process = self.running_processes[link]
        process.terminate()
        process.join(timeout=5)  # Give it a moment to die
        del self.running_processes[link]

    def check_dead_processes(self) -> None:
        """Check for dead processes and handle them appropriately."""
        dead_links = []
        for link, process in self.running_processes.items():
            if not process.is_alive():
                log.info(f'Thread {link} appears to be dead (404\'d or crashed).')
                dead_links.append(link)

        if not dead_links:
            return

        max_restarts = 3
        for link in dead_links:
            self._handle_dead_process(link, max_restarts)

    def _handle_dead_process(self, link: str, max_restarts: int) -> None:
        """Handle a dead process - check exit code, probe, and restart if needed.

        Args:
            link: The thread URL of the dead process.
            max_restarts: Maximum number of restart attempts.
        """
        log.info(f'Watcher for {link} appears to have stopped; probing and attempting restart.')

        proc = self.running_processes.get(link)
        exitcode = None
        if proc:
            try:
                exitcode = getattr(proc, 'exitcode', None)
            except Exception:
                pass

        # If exit code is 404, immediately disable
        if exitcode == 404:
            self._disable_link(link, reason='404')
            self.running_processes.pop(link, None)
            return

        # Quick probe: try to load the thread page to detect 404s
        is_404 = False
        try:
            self.http_client.fetch(link)
        except ThreadNotFoundError:
            is_404 = True
        except Exception:
            # Non-HTTP errors are ignored for the probe; we'll try restarts
            pass

        if is_404:
            self._disable_link(link, reason='404')
            self.running_processes.pop(link, None)
            return

        # Not a 404. Try restarting the watcher
        restarted = False
        for attempt in range(1, max_restarts + 1):
            try:
                old_proc = self.running_processes.pop(link, None)
                if old_proc is not None:
                    try:
                        old_proc.join(timeout=1)
                    except Exception:
                        pass

                new_proc = Process(
                    target=_call_watcher,
                    args=(link, self.config, self.workpath)
                )
                new_proc.start()
                time.sleep(1)  # Give it a moment to start
                if new_proc.is_alive():
                    self.running_processes[link] = new_proc
                    restarted = True
                    if self.config.verbose:
                        log.info(f'Restarted watcher for {link} (attempt {attempt})')
                    break
                else:
                    # Process died immediately; try again after backoff
                    try:
                        new_proc.join(timeout=1)
                    except Exception:
                        pass
            except Exception as e:
                log.warning(f'Attempt {attempt} to restart watcher for {link} failed: {e}')
            time.sleep(5 * attempt)

        if not restarted:
            self._disable_link(link, reason='after failed restarts')
            self.running_processes.pop(link, None)

    def _disable_link(self, link: str, reason: str) -> None:
        """Disable a link in the queue file by prefixing with '-'.

        Args:
            link: The thread URL to disable.
            reason: Reason for disabling (for logging).
        """
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            new_lines = []
            disabled = False
            for line in lines:
                stripped = line.strip()
                if stripped == link and not line.startswith('-'):
                    new_lines.append('-' + line)
                    disabled = True
                    log.info(f'Disabled {stripped} in {self.filename} ({reason})')
                else:
                    new_lines.append(line)
            if disabled:
                with open(self.filename, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
        except IOError as e:
            log.error(f'Error writing to file {self.filename}: {e}')

    def run(self) -> None:
        """Main run loop - manages watcher processes."""
        while True:
            # Load queue
            desired_links = self.load_queue()

            if self.config.verbose:
                log.info(
                    f'Loaded {len(desired_links)} links from {self.filename}; '
                    f'{len(self.running_processes)} watchers currently running.'
                )
                # Show which links are new vs already running
                current = set(self.running_processes.keys())
                new_links = desired_links - current
                removed = current - desired_links
                if new_links:
                    log.info('New links to start: ' + ', '.join(sorted(new_links)))
                if removed:
                    log.info('Links present but not in file: ' + ', '.join(sorted(removed)))

            if not desired_links and not self.running_processes:
                log.warning(f'{self.filename} is empty or all links are disabled.')

            # Check for dead processes
            self.check_dead_processes()

            # Start new processes for new links
            for link in desired_links:
                if link not in self.running_processes:
                    self.start_watcher(link)

            # Stop processes for links that have been removed from the file
            removed_links = [
                link for link in self.running_processes
                if link not in desired_links
            ]
            for link in removed_links:
                self.stop_watcher(link)

            if not self.config.reload:
                # If not reloading, wait for all spawned processes to complete
                for process in self.running_processes.values():
                    process.join()
                break
            else:
                # If reloading, wait for the specified time before checking again
                if self.config.verbose:
                    log.info(
                        f'Reloading {self.filename} in {self.config.reload_time} minutes. '
                        f'Watching {len(self.running_processes)} threads.'
                    )
                time.sleep(60 * self.config.reload_time)

