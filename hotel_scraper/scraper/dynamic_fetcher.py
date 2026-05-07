"""Browser-based fetcher for JavaScript-rendered sites using Playwright."""

import asyncio
import random

from loguru import logger
from playwright.async_api import async_playwright

from config import Config
from scraper.base_fetcher import BaseFetcher


class DynamicFetcher(BaseFetcher):
    """Fetches JS-rendered pages using headless Chromium via Playwright."""

    def fetch(self, url: str) -> str:
        """Synchronous entry point that wraps async logic.

        Args:
            url: Target URL.

        Returns:
            Full rendered HTML string.

        Raises:
            RuntimeError: If Playwright fails.
        """
        return asyncio.run(self._async_fetch(url))

    async def _async_fetch(self, url: str) -> str:
        """Async Playwright fetch with scroll to trigger lazy loading.

        Args:
            url: Target URL.

        Returns:
            Full rendered HTML string.
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=Config.USER_AGENT)
            page = await context.new_page()

            try:
                await page.goto(url, timeout=Config.TIMEOUT * 1000)
                await page.wait_for_load_state("networkidle")

                # Scroll to bottom to trigger lazy-loaded images
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)

                html = await page.content()
                logger.info(f"Fetched dynamic page: {url} ({len(html)} chars)")
                return html

            except Exception as e:
                logger.error(f"Dynamic fetch failed for {url}: {e}")
                raise RuntimeError(f"Dynamic fetch failed: {e}") from e

            finally:
                await browser.close()
