"""SQLite database operations for hash storage."""
import sqlite3
import time
import logging
from typing import Optional, Set
import os
from contextlib import contextmanager

from .config import DB_PATH_DEFAULT, DB_TIMEOUT
from .exceptions import DatabaseError

log = logging.getLogger('inb4404')


class HashDB:
    """Manages SQLite database operations for MD5 hash storage."""

    def __init__(self, db_path: Optional[str] = None, timeout: int = DB_TIMEOUT):
        """Initialize the HashDB instance.

        Args:
            db_path: Path to the SQLite database file. If None, uses default.
            timeout: Database connection timeout in seconds.
        """
        if db_path is None:
            # Calculate default path based on workpath
            from .config import DEFAULT_WORKPATH, DB_PATH_DEFAULT
            self.db_path = os.path.join(DEFAULT_WORKPATH, DB_PATH_DEFAULT)
        else:
            self.db_path = db_path
        self.timeout = timeout
        self.init()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=self.timeout)
            yield conn
        except Exception as e:
            log.warning(f'Database operation failed: {e}')
            raise DatabaseError(f'Database operation failed: {e}') from e
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def init(self) -> None:
        """Ensure the SQLite database and the required table exist.

        This function is idempotent and safe to call multiple times. It sets
        `journal_mode=WAL` to improve concurrency between processes.
        """
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute('PRAGMA journal_mode=WAL;')
                cur.execute(
                    'CREATE TABLE IF NOT EXISTS hashes '
                    '(md5 TEXT PRIMARY KEY, path TEXT, thread TEXT, ts INTEGER)'
                )
                conn.commit()
        except Exception as e:
            log.warning(f'Could not initialize hashes DB: {e}')

    def get_path(self, md5: str) -> Optional[str]:
        """Return stored path for `md5` or None when not present.

        Args:
            md5: The MD5 hash to look up.

        Returns:
            The file path associated with the MD5 hash, or None if not found.
        """
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute('SELECT path FROM hashes WHERE md5=?', (md5,))
                row = cur.fetchone()
                return row[0] if row else None
        except Exception:
            return None

    def has_hash(self, md5: str) -> bool:
        """Check if the given MD5 hash exists in the database.

        Args:
            md5: The MD5 hash to check.

        Returns:
            True if the hash exists, False otherwise.
        """
        return self.get_path(md5) is not None

    def insert(self, md5: str, path: str, thread_name: str) -> None:
        """Insert md5->path mapping. Uses INSERT OR IGNORE to avoid races.

        Args:
            md5: The MD5 hash of the file.
            path: The file path.
            thread_name: The name/ID of the thread.
        """
        try:
            with self._get_connection() as conn:
                conn.execute(
                    'INSERT OR IGNORE INTO hashes (md5, path, thread, ts) VALUES (?,?,?,?)',
                    (md5, path, thread_name, int(time.time()))
                )
        except Exception as e:
            log.warning(f'Could not write to hashes DB: {e}')

    def upsert(self, md5: str, path: str, thread_name: str) -> None:
        """Insert or replace the md5->path mapping.

        Used after dedupe to ensure the DB points to the kept file path.

        Args:
            md5: The MD5 hash of the file.
            path: The file path.
            thread_name: The name/ID of the thread.
        """
        try:
            with self._get_connection() as conn:
                conn.execute(
                    'INSERT OR REPLACE INTO hashes (md5, path, thread, ts) VALUES (?,?,?,?)',
                    (md5, path, thread_name, int(time.time()))
                )
        except Exception as e:
            log.warning(f'Could not upsert into hashes DB: {e}')

    def get_thread_hashes(self, thread_id: str) -> Set[str]:
        """Get all MD5 hashes for a specific thread.

        Args:
            thread_id: The numeric thread ID.

        Returns:
            A set of MD5 hashes for the thread.
        """
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute('SELECT md5 FROM hashes WHERE thread=?', (thread_id,))
                rows = cur.fetchall()
                return {r[0] for r in rows if r and r[0]}
        except Exception:
            return set()

    def count_hashes(self) -> int:
        """Get the total count of hashes in the database.

        Returns:
            The number of hashes in the database.
        """
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute('SELECT COUNT(*) FROM hashes')
                row = cur.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

