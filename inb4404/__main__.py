"""Main entry point for inb4404."""
import argparse
import logging
import os
import sys

from .config import Config
from .database import HashDB
from .thread_watcher import ThreadWatcher
from .process_manager import ProcessManager
from .deduplicator import Deduplicator

log = logging.getLogger('inb4404')


def create_config_from_args(args: argparse.Namespace) -> Config:
    """Create a Config object from parsed arguments.

    Args:
        args: Parsed command-line arguments.

    Returns:
        A Config object with settings from arguments.
    """
    # Calculate workpath - directory where inb4404.py is located
    # This handles both running as package and as script
    if __file__.endswith('__main__.py'):
        # Running as package
        workpath = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    else:
        # Running as script (shouldn't happen, but handle it)
        workpath = os.path.dirname(os.path.realpath(__file__))
    
    # If inb4404.py exists in the parent directory, use that directory
    script_path = os.path.join(workpath, 'inb4404.py')
    if os.path.exists(script_path):
        workpath = os.path.dirname(script_path)
    
    return Config(
        workpath=workpath,
        refresh_time=getattr(args, 'refresh_time', 20.0),
        reload_time=getattr(args, 'reload_time', 5.0),
        throttle=getattr(args, 'throttle', 0.5),
        backoff=getattr(args, 'backoff', 0.5),
        verbose=getattr(args, 'verbose', False),
        date=getattr(args, 'date', False),
        with_counter=getattr(args, 'with_counter', False),
        use_names=getattr(args, 'use_names', False),
        reload=getattr(args, 'reload', False),
        title=getattr(args, 'title', False),
        subject=getattr(args, 'subject', False),
        new_dir=getattr(args, 'new_dir', False),
        origin_name=getattr(args, 'origin_name', False),
        dedupe_downloads=getattr(args, 'dedupe_downloads', False),
    )


def setup_logging(config: Config) -> None:
    """Set up logging configuration.

    Args:
        config: Configuration settings.
    """
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


def main() -> None:
    """Entry point for the script.

    Parses command-line arguments and either starts a watcher for a single
    thread URL or treats the provided argument as a filename containing a
    list of thread URLs (one per line).
    """
    parser = argparse.ArgumentParser(description='inb4404')

    parser.add_argument(
        'thread',
        nargs='?',
        help='url of the thread (or filename; one url per line)'
    )
    parser.add_argument(
        '-c', '--with-counter',
        action='store_true',
        help='show a counter next the the image that has been downloaded'
    )
    parser.add_argument(
        '-d', '--date',
        action='store_true',
        help='show date as well'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='show more information'
    )
    parser.add_argument(
        '-l', '--less',
        action='store_true',
        help=argparse.SUPPRESS
    )
    parser.add_argument(
        '-n', '--use-names',
        action='store_true',
        help='use thread names instead of the thread ids (...4chan.org/board/thread/thread-id/thread-name)'
    )
    parser.add_argument(
        '-r', '--reload',
        action='store_true',
        help='reload the queue file every 5 minutes'
    )
    parser.add_argument(
        '-t', '--title',
        action='store_true',
        help='save original filenames'
    )
    parser.add_argument(
        '--no-subject',
        dest='subject',
        action='store_false',
        default=True,
        help="disable using thread subject in directory name (enabled by default)"
    )
    parser.add_argument(
        '--new-dir',
        action='store_true',
        help='create the `new` directory'
    )
    parser.add_argument(
        '--refresh-time',
        type=float,
        default=20,
        help='Delay in seconds before refreshing the thread'
    )
    parser.add_argument(
        '--reload-time',
        type=float,
        default=5,
        help='Delay in minutes before reloading the file. Default: 5'
    )
    parser.add_argument(
        '--throttle',
        type=float,
        default=0.5,
        help='Delay in seconds between downloads in the same thread'
    )
    parser.add_argument(
        '--backoff',
        type=float,
        default=0.5,
        help='Delay in seconds by which throttle should increase on 429'
    )
    parser.add_argument(
        '--origin-name',
        action='store_true',
        help='save files using the original filename when available (strip server numeric prefix when possible)'
    )
    parser.add_argument(
        '--dedupe-downloads',
        action='store_true',
        help='scan downloads directory, keep oldest file per hash and delete duplicate files'
    )

    args = parser.parse_args()

    # Create config from arguments
    config = create_config_from_args(args)

    # Ensure the SQLite DB exists before starting any workers
    db_path = os.path.join(config.workpath, 'hashes.db')
    db = HashDB(db_path=db_path)
    db.init()

    # If requested, run dedupe pass across the entire downloads directory
    # and then exit. This can be run without providing the positional
    # `thread` argument.
    if config.dedupe_downloads:
        setup_logging(config)
        deduplicator = Deduplicator(config, config.workpath)
        deduplicator.run()
        return

    # Set up logging
    setup_logging(config)

    if getattr(args, 'less', False):
        log.info("'--less' is now the default behavior. Use '--verbose' to increase output detail.")

    # Check for optional dependencies if --title is used
    if config.title:
        try:
            import bs4  # noqa: F401
            import django  # noqa: F401
        except ImportError:
            log.error('Could not import the required modules! Disabling --title option...')
            config.title = False

    # At this point the `thread` positional may be None (if omitted). If it
    # is missing and we didn't take an early-exit like `--dedupe-downloads`,
    # treat that as a usage error.
    if not args.thread:
        parser.error('the following argument is required: thread (unless --dedupe-downloads is used)')

    thread = args.thread.strip()
    if thread[:4].lower() == 'http':
        # Single thread URL
        watcher = ThreadWatcher(thread, config, config.workpath)
        watcher.watch()
    else:
        # File containing thread URLs
        manager = ProcessManager(thread, config, config.workpath)
        manager.run()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass

