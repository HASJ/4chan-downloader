"""Custom exception classes for inb4404."""


class Inb4404Error(Exception):
    """Base exception for all inb4404 errors."""
    pass


class ThreadNotFoundError(Inb4404Error):
    """Raised when a thread cannot be found (404)."""
    pass


class DownloadError(Inb4404Error):
    """Raised when a file download fails."""
    pass


class DatabaseError(Inb4404Error):
    """Raised when a database operation fails."""
    pass


class HTTPError(Inb4404Error):
    """Raised when an HTTP request fails."""
    pass

