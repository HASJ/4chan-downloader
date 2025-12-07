"""Configuration constants and settings for inb4404."""
import os
from dataclasses import dataclass
from typing import Optional


# Default workpath - will be set by main entry point
# This is the directory where inb4404.py is located (or where the script is run from)
DEFAULT_WORKPATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

# Path to SQLite database used for global MD5 -> path mapping
# Will be calculated based on workpath in Config
DB_PATH_DEFAULT = 'hashes.db'

# Default configuration values
DEFAULT_REFRESH_TIME = 20.0  # seconds
DEFAULT_RELOAD_TIME = 5.0  # minutes
DEFAULT_THROTTLE = 0.5  # seconds
DEFAULT_BACKOFF = 0.5  # seconds
DB_TIMEOUT = 30  # seconds


@dataclass
class Config:
    """Configuration settings for the application."""
    workpath: str = DEFAULT_WORKPATH
    db_path: str = os.path.join(DEFAULT_WORKPATH, DB_PATH_DEFAULT)
    refresh_time: float = DEFAULT_REFRESH_TIME
    reload_time: float = DEFAULT_RELOAD_TIME
    throttle: float = DEFAULT_THROTTLE
    backoff: float = DEFAULT_BACKOFF
    db_timeout: int = DB_TIMEOUT
    verbose: bool = False
    date: bool = False
    with_counter: bool = False
    use_names: bool = False
    reload: bool = False
    title: bool = False
    subject: bool = False
    new_dir: bool = False
    origin_name: bool = False
    dedupe_downloads: bool = False

