"""Thread URL parsing and metadata extraction."""
import re
import html
import logging
from dataclasses import dataclass
from typing import Optional, List, Union
from urllib.parse import urlparse

from .http_client import HTTPClient
from .file_utils import FileManager

log = logging.getLogger('inb4404')


@dataclass
class ThreadURL:
    """Parsed thread URL information."""
    url: str
    board: str
    thread_id: str
    slug: Optional[str] = None

    @classmethod
    def parse(cls, url: str) -> 'ThreadURL':
        """Parse a thread URL into components.

        Args:
            url: The thread URL to parse.

        Returns:
            A ThreadURL instance with parsed components.
        """
        # Remove fragment if present
        url = url.split('#')[0]
        parts = url.split('/')
        
        # Find the board (typically at index 3: https://boards.4chan.org/board/thread/...)
        board = parts[3] if len(parts) > 3 else ''
        
        # Find thread_id (typically at index 5)
        thread_id = parts[5] if len(parts) > 5 else ''
        
        # Find slug if present (typically at index 6)
        slug = parts[6] if len(parts) > 6 else None
        
        return cls(url=url, board=board, thread_id=thread_id, slug=slug)


class ThreadParser:
    """Parses thread URLs and extracts metadata."""

    def __init__(self, http_client: Optional[HTTPClient] = None):
        """Initialize the ThreadParser.

        Args:
            http_client: Optional HTTPClient instance. If None, creates a new one.
        """
        self.http_client = http_client or HTTPClient()

    def parse_url(self, url: str) -> ThreadURL:
        """Parse a thread URL.

        Args:
            url: The thread URL to parse.

        Returns:
            A ThreadURL instance with parsed components.
        """
        return ThreadURL.parse(url)

    def get_subject(self, board: str, thread_id: str) -> Optional[str]:
        """Retrieve the subject of a thread (or a comment snippet).

        Attempts to fetch the thread via the 4chan JSON API first. If successful,
        returns the 'sub' (subject) field if present, or a snippet of the 'com'
        (comment) field. If the API fails, attempts to scrape the subject from
        the HTML.

        Args:
            board: The board identifier (e.g., 'g', 'wg').
            thread_id: The numeric thread ID.

        Returns:
            The sanitized subject/snippet, or None if retrieval failed.
        """
        # 1. Try JSON API
        try:
            thread_json = self.http_client.fetch_thread_api(board, thread_id)
            if thread_json:
                posts = thread_json.get('posts', [])
                if posts:
                    op = posts[0]
                    # Prefer 'sub' (Subject)
                    if 'sub' in op:
                        return FileManager.sanitize_filename(html.unescape(op['sub']))
                    # Fallback to 'com' (Comment)
                    if 'com' in op:
                        comment = op['com']
                        # Strip HTML tags
                        comment = re.sub(r'<[^>]+>', '', comment)
                        comment = html.unescape(comment)
                        # Truncate to a reasonable length (e.g. 50 chars)
                        if len(comment) > 50:
                            comment = comment[:50].strip() + '...'
                        return FileManager.sanitize_filename(comment)
        except Exception as e:
            log.debug(f"Failed to fetch subject via API for {board}/{thread_id}: {e}")

        # 2. Fallback to HTML scraping
        try:
            thread_url = f'https://boards.4chan.org/{board}/thread/{thread_id}'
            html_content = self.http_client.fetch(thread_url).decode('utf-8')
            # Regex for subject: <span class="subject">Subject Here</span>
            match = re.search(r'<span class="subject">([^<]+)</span>', html_content)
            if match:
                return FileManager.sanitize_filename(html.unescape(match.group(1)))
        except Exception as e:
            log.debug(f"Failed to fetch subject via HTML for {board}/{thread_id}: {e}")

        return None

    def extract_titles(self, html_content: Union[str, bytes]) -> List[str]:
        """Parse the HTML content and extract the 'title' attribute from file links.

        This is used when the `--title` flag is set to preserve the filename/title
        supplied in the post rather than the server numeric name. Falls back to
        link text when the title attribute is missing.

        Args:
            html_content: The HTML content of the thread (str or bytes).

        Returns:
            A list of titles/filenames extracted from the HTML.
        """
        ret = []

        try:
            from bs4 import BeautifulSoup, element as bs4_element
        except ImportError:
            log.warning("BeautifulSoup4 not available, cannot extract titles from HTML")
            return ret

        if isinstance(html_content, bytes):
            html_content = html_content.decode('utf-8')

        parsed = BeautifulSoup(html_content, 'html.parser')
        divs = parsed.find_all("div", {"class": "fileText"})

        for i in divs:
            # The structure on typical imageboard HTML is that fileText contains
            # an <a> child describing the file; we take the first direct <a> child.
            # Guard against non-Tag nodes (NavigableString/PageElement) to satisfy
            # static analyzers and avoid attribute errors.
            if not isinstance(i, bs4_element.Tag):
                continue

            anchors = i.find_all("a", recursive=False)
            if not anchors:
                continue

            first_child = anchors[0]
            # Prefer the `title` attribute (original filename) when present,
            # otherwise fall back to the link text.
            # Some find_all results may produce non-Tag nodes (NavigableString / PageElement)
            # which do not implement .get(); check the type first to satisfy static analyzers.
            if isinstance(first_child, bs4_element.Tag):
                title = first_child.get("title")
                if title:
                    ret.append(title)
                else:
                    ret.append(first_child.text)
            else:
                # Fallback: use the node's string content or its string representation.
                text = getattr(first_child, 'string', None)
                if text:
                    ret.append(text)
                else:
                    ret.append(str(first_child))

        return ret

