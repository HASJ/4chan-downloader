#!/usr/bin/python3
# inb4404.py
#
# Lightweight thread watcher/downloader for 4chan-style imageboard threads.
# This is a backward-compatible entry point that delegates to the new package structure.
#
# For the refactored implementation, see the inb4404 package.

if __name__ == '__main__':
    # Import and run the main function from the package
    from inb4404.__main__ import main
    try:
        main()
    except KeyboardInterrupt:
        # Graceful exit on Ctrl+C from the user (avoid full traceback)
        pass