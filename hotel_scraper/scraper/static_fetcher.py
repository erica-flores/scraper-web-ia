"""HTTP fetcher for static sites using requests + tenacity retry."""

import random
import time

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config import Config
from scraper.base_fetcher import BaseFetcher


class StaticFetcher(BaseFetcher):
    """Fetches static HTML pages using requests."""

    def __init__(self) -> None:
        """Initialize with session and headers."""
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": Config.USER_AGENT})

    @retry(
        stop=stop_after_attempt(Config.MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def fetch(self, url: str) -> str:
        """Fetch HTML from a static site.

        Args:
            url: Target URL.

        Returns:
            HTML string.

        Raises:
            RuntimeError: If all retries fail.
        """
        delay = random.uniform(Config.DELAY_MIN, Config.DELAY_MAX)
        time.sleep(delay)

        try:
            response = self.session.get(url, timeout=Config.TIMEOUT)
            response.raise_for_status()
            logger.info(f"Fetched static page: {url} ({len(response.text)} chars)")
            return response.text
        except requests.RequestException as e:
            logger.error(f"Static fetch failed for {url}: {e}")
            raise RuntimeError(f"Static fetch failed: {e}") from e
