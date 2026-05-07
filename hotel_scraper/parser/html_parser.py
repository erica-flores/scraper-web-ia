"""Core HTML parser wrapping BeautifulSoup4 with lxml backend."""

from bs4 import BeautifulSoup
from loguru import logger


class HTMLParser:
    """Parses raw HTML strings into BeautifulSoup objects."""

    def __init__(self, html: str) -> None:
        """Initialize parser with raw HTML.

        Args:
            html: Raw HTML string from any fetcher.
        """
        self.soup = BeautifulSoup(html, "lxml")
        self.html = html
        logger.debug(f"HTMLParser initialized. Tags found: {len(self.soup.find_all())}")

    def get_soup(self) -> BeautifulSoup:
        """Return the BeautifulSoup object.

        Returns:
            Parsed BeautifulSoup object.
        """
        return self.soup

    def get_text(self) -> str:
        """Return all visible text stripped of tags.

        Returns:
            Plain text string.
        """
        return self.soup.get_text(separator=" ", strip=True)
