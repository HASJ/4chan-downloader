# inb4404 - 4chan Thread Downloader

`inb4404` is a fork from [Exceen/4chan-downloader](https://github.com/Exceen/4chan-downloader), a lightweight, command-line utility for watching and downloading media from 4chan-style imageboard threads. It is designed to be efficient and resilient, making it easy to archive threads automatically.
The main functionality added of this fork is the dupe checker.

## Features

- **Continuous Monitoring**: Watches one or more threads and automatically downloads new images and videos as they are posted.
- **Duplicate Prevention**: Maintains a global database of file hashes (MD5) to prevent downloading the same file multiple times, even across different threads.
- **Multi-Threading**: Can monitor multiple threads simultaneously by reading a list of URLs from a file.
- **Intelligent Backoff**: Automatically adjusts request frequency when rate-limited (HTTP 429).
- **Dead Thread Handling**: Detects when a thread has 404'd and can automatically disable it in the queue file.
- **Flexible Naming**: Save files using their original filenames or the server-generated names.
- **Deduplication Utility**: Includes a tool to scan your existing download archive, find duplicate files, and remove them, keeping only the oldest copy.
- **Resilient API Usage**: Prefers the 4chan JSON API for efficiency but falls back gracefully to HTML scraping if the API is unavailable.
- **Cross-Platform**: Written in Python and should run on any major operating system.

## Requirements

- Python 3.6+
- No external libraries are required for basic functionality.

For the optional `--title` feature (to save files with their original post title), the following libraries are needed:

- `beautifulsoup4`
- `django` (used for `get_valid_filename`)

## Installation

1. Clone this repository:

   ```bash
   git clone <repository-url>
   cd inb4404
   ```
2. (Optional) To use the `--title` feature, install the required libraries:

   ```bash
   pip install beautifulsoup4 django
   ```

## Usage

The script can be run in two main modes: watching a single thread or watching multiple threads from a file.

### Watching a Single Thread

To watch a single thread, simply provide the URL as an argument:

```bash
python inb4404.py <thread-url>
```

**Example:**

```bash
python inb4404.py https://boards.4chan.org/wg/thread/7654321
```

### Watching Multiple Threads

1. Create a text file (e.g., `threads.txt`).
2. Add one thread URL per line.
3. Run the script with the filename as the argument.

**Example `threads.txt`:**

```
https://boards.4chan.org/wg/thread/7654321
https://boards.4chan.org/hr/thread/1234567
```

**Run the script:**

```bash
python inb4404.py threads.txt
```

By default, the script will only process the file once. Use the `--reload` flag to have the script periodically re-read the file for changes.

### Command-Line Arguments

Here are some of the most common options:

| Argument                   | Description                                                                              |
| -------------------------- | ---------------------------------------------------------------------------------------- |
| `thread`                 | The URL of the thread to watch, or a path to a file containing a list of URLs.           |
| `-c`, `--with-counter` | Show a download counter (`[1/100]`).                                                   |
| `-d`, `--date`         | Show the date in the log output.                                                         |
| `-v`, `--verbose`      | Show more detailed logging information.                                                  |
| `-n`, `--use-names`    | Use thread names for directory paths instead of thread IDs.                              |
| `-r`, `--reload`       | Reload the queue file every 5 minutes for new or removed threads.                        |
| `-t`, `--title`        | Save files using the post's title as the filename (requires optional libraries).         |
| `--new-dir`              | Create a separate `new` directory for recent downloads (default: off).                   |
| `--no-subject`           | Do not include the thread subject in the download directory name.                        |
| `--origin-name`          | Save files using the original filename given on the board.                               |
| `--refresh-time SEC`     | Time in seconds to wait before refreshing a thread (default: 20).                        |
| `--reload-time MIN`      | Delay in minutes before reloading the file (default: 5).                                 |
| `--throttle SEC`         | Delay in seconds between downloads within the same thread (default: 0.5).                |
| `--backoff SEC`          | Delay in seconds by which throttle should increase on 429 errors (default: 0.5).         |
| `--dedupe-downloads`     | Run a scan of the `downloads` directory to find and remove duplicate files, then exit. |

For a full list of commands, run:

```bash
python inb4404.py --help
```

### Deduplicating Existing Downloads

If you have an existing archive, you can use the `--dedupe-downloads` flag to clean it up. This will scan all files in the `downloads` directory, identify files with identical content, and delete all but the oldest copy of each file.

```bash
python inb4404.py --dedupe-downloads
```

## Contributing

Contributions are welcome! If you have a feature request, bug report, or a pull request, please open an issue or PR on the GitHub repository.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
