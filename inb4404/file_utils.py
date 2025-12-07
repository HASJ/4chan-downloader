"""File operations, naming, and MD5 hashing utilities."""
import os
import re
import hashlib
from typing import Optional

try:
    from django.utils.text import get_valid_filename as django_get_valid_filename
    HAS_DJANGO = True
except ImportError:
    HAS_DJANGO = False


class FileManager:
    """Manages file operations, naming, and hashing."""

    @staticmethod
    def sanitize_filename(s: str) -> str:
        """Sanitize a string to be safe for use as a filename.

        Removes non-word characters (except for dots, dashes, and spaces) and
        replaces spaces with underscores if Django is not available.

        Args:
            s: The string to sanitize.

        Returns:
            The sanitized filename.
        """
        if HAS_DJANGO:
            return django_get_valid_filename(s)

        s = str(s).strip()
        # remove characters that are not word chars, dot, dash or space
        s = re.sub(r'(?u)[^-\w.\s]', '', s)
        # replace spaces with underscores to produce a safe filename
        s = s.replace(' ', '_')
        if not s:
            s = 'file'
        return s

    @staticmethod
    def compute_hash(file_path: str) -> Optional[str]:
        """Compute and return the MD5 hex digest of a file's contents.

        Args:
            file_path: The path to the file.

        Returns:
            The MD5 hex digest, or None if the file cannot be read.
        """
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                # Read in chunks to avoid high memory usage on large files.
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
        except IOError:
            return None
        return hash_md5.hexdigest()

    @staticmethod
    def ensure_directory(directory: str) -> None:
        """Ensure a directory exists, creating it if necessary.

        Args:
            directory: The directory path to ensure exists.
        """
        if not os.path.exists(directory):
            os.makedirs(directory)

    @staticmethod
    def compute_hash_bytes(data: bytes) -> str:
        """Compute MD5 hash of bytes data.

        Args:
            data: The bytes to hash.

        Returns:
            The MD5 hex digest.
        """
        return hashlib.md5(data).hexdigest()


# Convenience functions for backward compatibility
def clean_filename(s: str) -> str:
    """Sanitize a string to be safe for use as a filename.

    Args:
        s: The string to sanitize.

    Returns:
        The sanitized filename.
    """
    return FileManager.sanitize_filename(s)


def get_md5(file_path: str) -> Optional[str]:
    """Compute and return the MD5 hex digest of a file's contents.

    Args:
        file_path: The path to the file.

    Returns:
        The MD5 hex digest, or None if the file cannot be read.
    """
    return FileManager.compute_hash(file_path)

