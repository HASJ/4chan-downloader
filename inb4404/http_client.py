"""HTTP client for fetching thread data and files."""
import urllib.request
import urllib.error
import urllib.parse
import json
import logging
from typing import Dict, Any, Optional

from .exceptions import HTTPError, ThreadNotFoundError

log = logging.getLogger('inb4404')


class HTTPClient:
    """Handles HTTP requests for thread data and file downloads."""

    USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15'

    def __init__(self):
        """Initialize the HTTP client."""
        pass

    def _build_headers(self, url: str) -> Dict[str, str]:
        """Build HTTP headers for a request.

        Args:
            url: The URL to fetch.

        Returns:
            A dictionary of HTTP headers.
        """
        parsed = urllib.parse.urlparse(url)
        path_parts = parsed.path.strip('/').split('/')
        referer = f'{parsed.scheme}://{parsed.netloc}/{path_parts[0]}' if path_parts else url

        return {
            'User-Agent': self.USER_AGENT,
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-User': '?1',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': referer,
            'Connection': 'keep-alive',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Priority': 'u=0, i',
            'TE': 'trailers',
        }

    def fetch(self, url: str) -> bytes:
        """Perform an HTTP GET and return the raw bytes of the response.

        A Request object is used with common headers (User-Agent, Referer,
        Accept-Language etc.) to mimic a modern browser and avoid basic
        anti-bot measures. The referer is derived from the URL's board root so
        that some hosts accept the request.

        Args:
            url: The URL to fetch.

        Returns:
            The raw content of the response.

        Raises:
            HTTPError: If the request fails.
            ThreadNotFoundError: If the response is 404.
        """
        try:
            # Normalize protocol-relative URLs
            if url.startswith('//'):
                url = 'https:' + url

            headers = self._build_headers(url)
            req = urllib.request.Request(url, headers=headers)
            response = urllib.request.urlopen(req)
            return response.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise ThreadNotFoundError(f'Thread not found: {url}') from e
            raise HTTPError(f'HTTP error {e.code} for {url}') from e
        except urllib.error.URLError as e:
            raise HTTPError(f'URL error for {url}: {e}') from e
        except Exception as e:
            raise HTTPError(f'Unexpected error fetching {url}: {e}') from e

    def fetch_json(self, url: str) -> Dict[str, Any]:
        """Fetch a URL and parse the response as JSON.

        Args:
            url: The URL to fetch.

        Returns:
            The parsed JSON data.

        Raises:
            HTTPError: If the request fails or JSON parsing fails.
        """
        try:
            data = self.fetch(url)
            return json.loads(data.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise HTTPError(f'Failed to parse JSON from {url}: {e}') from e

    def fetch_thread_api(self, board: str, thread_id: str) -> Optional[Dict[str, Any]]:
        """Fetch thread data from the 4chan JSON API.

        Args:
            board: The board identifier (e.g., 'g', 'wg').
            thread_id: The numeric thread ID.

        Returns:
            The parsed thread JSON data, or None if the API is unavailable.
        """
        try:
            api_url = f'https://a.4cdn.org/{board}/thread/{thread_id}.json'
            # Use simpler headers for API requests
            req = urllib.request.Request(api_url, headers={'User-Agent': self.USER_AGENT})
            response = urllib.request.urlopen(req)
            data = response.read().decode('utf-8')
            return json.loads(data)
        except Exception as e:
            log.debug(f"Failed to fetch thread API for {board}/{thread_id}: {e}")
            return None

