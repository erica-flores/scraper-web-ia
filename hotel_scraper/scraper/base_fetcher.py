"""Abstract base class for all fetchers."""

from abc import ABC, abstractmethod


class BaseFetcher(ABC):
    """All fetchers must implement fetch()."""

    @abstractmethod
    def fetch(self, url: str) -> str:
        """Fetch the full HTML content of a URL.

        Args:
            url: The target URL to fetch.

        Returns:
            Full HTML string of the page.

        Raises:
            RuntimeError: If fetch fails after all retries.
        """
