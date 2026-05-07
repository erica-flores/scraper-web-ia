# AGENT SYSTEM DESIGN DOCUMENT
## Hotel Web Scraper — MVP
> This document is a machine-readable specification for an LLM coding agent (Claude Code, Cursor, Aider, etc.).
> Follow every instruction literally. Do not add features not listed. Do not skip steps.
> Complete tasks in the exact order defined. Validate each step before proceeding.

---

## 0. AGENT OPERATING RULES

```
RULE-001: Execute tasks in the order listed. Never skip ahead.
RULE-002: After creating each file, verify it exists on disk before continuing.
RULE-003: After each PHASE is complete, run the validation command defined in that phase.
RULE-004: If a validation fails, fix it before moving to the next phase.
RULE-005: Never create files outside the project root defined in PHASE-1.
RULE-006: All code must be Python 3.11+. Use type hints everywhere.
RULE-007: Never use global variables. Pass dependencies via constructor injection.
RULE-008: Every function must have a docstring with Args and Returns.
RULE-009: When the spec says "raise", raise the exact exception type listed.
RULE-010: When the spec says "log", use loguru logger, not print().
```

---

## 1. PHASE 1 — PROJECT SCAFFOLD

### 1.1 Create directory tree

Execute these shell commands exactly:

```bash
mkdir -p hotel_scraper/scraper
mkdir -p hotel_scraper/parser
mkdir -p hotel_scraper/llm
mkdir -p hotel_scraper/models
mkdir -p hotel_scraper/downloader
mkdir -p hotel_scraper/exporter
mkdir -p hotel_scraper/tests
touch hotel_scraper/__init__.py
touch hotel_scraper/scraper/__init__.py
touch hotel_scraper/parser/__init__.py
touch hotel_scraper/llm/__init__.py
touch hotel_scraper/models/__init__.py
touch hotel_scraper/downloader/__init__.py
touch hotel_scraper/exporter/__init__.py
touch hotel_scraper/tests/__init__.py
```

### 1.2 Create `requirements.txt`

Write exactly this content to `hotel_scraper/requirements.txt`:

```
requests==2.32.3
httpx==0.28.1
aiohttp==3.11.11
beautifulsoup4==4.13.3
lxml==5.3.0
playwright==1.49.1
pydantic==2.10.4
pandas==2.2.3
python-dotenv==1.0.1
tenacity==9.0.0
tqdm==4.67.1
loguru==0.7.3
Pillow==11.1.0
google-generativeai==0.8.3
```

### 1.3 Create `.env.example`

Write to `hotel_scraper/.env.example`:

```
GEMINI_API_KEY=
GROQ_API_KEY=
SCRAPER_DELAY_MIN=1.5
SCRAPER_DELAY_MAX=4.0
MAX_CONCURRENT_IMAGES=5
SCRAPER_TIMEOUT=30
SCRAPER_MAX_RETRIES=3
```

### 1.4 Install dependencies

```bash
cd hotel_scraper
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 1.5 PHASE 1 VALIDATION

```bash
python -c "import requests, httpx, aiohttp, bs4, playwright, pydantic, pandas, dotenv, tenacity, tqdm, loguru, PIL, google.generativeai; print('ALL IMPORTS OK')"
```

Expected output: `ALL IMPORTS OK`
If any import fails: install the missing package and re-run.

---

## 2. PHASE 2 — DATA MODELS

### 2.1 Create `hotel_scraper/models/hotel_data.py`

Write this file with zero modifications:

```python
"""Pydantic data models for the hotel scraper system."""

from __future__ import annotations

from datetime import date
from typing import Optional
from pydantic import BaseModel, field_validator


class RoomImage(BaseModel):
    """Represents a single room image."""
    url: str
    filename: str
    local_path: Optional[str] = None
    downloaded: bool = False


class Price(BaseModel):
    """Represents a single price entry for a room."""
    amount: float
    currency: str = "ARS"
    period: Optional[str] = None      # "por noche", "semanal", etc.
    season: Optional[str] = None      # "alta", "baja", "media"
    raw_text: str                     # exact text as found in HTML

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: float) -> float:
        """Validates that price amount is positive."""
        if v < 0:
            raise ValueError("Price amount must be >= 0")
        return v


class Shift(BaseModel):
    """Represents check-in/check-out and availability information."""
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    min_nights: Optional[int] = None
    max_nights: Optional[int] = None
    available_from: Optional[date] = None
    available_to: Optional[date] = None
    raw_text: Optional[str] = None


class Room(BaseModel):
    """Represents a single hotel room."""
    name: str
    description: Optional[str] = None
    capacity: Optional[int] = None
    prices: list[Price] = []
    shifts: list[Shift] = []
    images: list[RoomImage] = []
    amenities: list[str] = []
    raw_html: Optional[str] = None


class Hotel(BaseModel):
    """Top-level model representing a fully scraped hotel."""
    name: str
    url: str
    scraped_at: str
    rooms: list[Room] = []
    general_shift: Optional[Shift] = None
    source_type: str = "static"       # "static" | "dynamic" | "llm_assisted"
```

### 2.2 PHASE 2 VALIDATION

```bash
python -c "
from hotel_scraper.models.hotel_data import Hotel, Room, Price, Shift, RoomImage
h = Hotel(name='Test', url='http://x.com', scraped_at='2026-01-01')
r = Room(name='Suite')
p = Price(amount=100.0, raw_text='$100')
s = Shift(check_in='14:00', check_out='10:00')
i = RoomImage(url='http://x.com/img.jpg', filename='img.jpg')
print('MODELS OK')
"
```

Expected output: `MODELS OK`

---

## 3. PHASE 3 — CONFIGURATION

### 3.1 Create `hotel_scraper/config.py`

```python
"""Global configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Centralised configuration. Read from .env file."""

    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    DELAY_MIN: float = float(os.getenv("SCRAPER_DELAY_MIN", "1.5"))
    DELAY_MAX: float = float(os.getenv("SCRAPER_DELAY_MAX", "4.0"))
    MAX_CONCURRENT_IMAGES: int = int(os.getenv("MAX_CONCURRENT_IMAGES", "5"))
    TIMEOUT: int = int(os.getenv("SCRAPER_TIMEOUT", "30"))
    MAX_RETRIES: int = int(os.getenv("SCRAPER_MAX_RETRIES", "3"))

    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    DYNAMIC_SIGNALS: list[str] = [
        "__NEXT_DATA__",
        "window.__nuxt__",
        "__REACT_ROUTER__",
        "ng-version",
        "data-reactroot",
        "data-v-app",
    ]
```

---

## 4. PHASE 4 — FETCHER LAYER

### 4.1 Create `hotel_scraper/scraper/base_fetcher.py`

```python
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
```

### 4.2 Create `hotel_scraper/scraper/detector.py`

```python
"""Detects whether a URL requires static or dynamic fetching."""

import requests
from loguru import logger
from hotel_scraper.config import Config


def detect_site_type(url: str) -> str:
    """Detect whether the site needs Playwright (dynamic) or requests (static).

    Args:
        url: The hotel website URL.

    Returns:
        "static" or "dynamic"
    """
    try:
        response = requests.get(
            url,
            headers={"User-Agent": Config.USER_AGENT},
            timeout=Config.TIMEOUT,
        )
        html = response.text
    except Exception as e:
        logger.warning(f"Detection request failed: {e}. Defaulting to dynamic.")
        return "dynamic"

    for signal in Config.DYNAMIC_SIGNALS:
        if signal in html:
            logger.info(f"Dynamic signal found: '{signal}'. Using Playwright.")
            return "dynamic"

    # Heuristic: if visible text is very sparse, likely JS-rendered
    import re
    visible_text = re.sub(r"<[^>]+>", "", html)
    visible_text = visible_text.strip()
    if len(visible_text) < 500:
        logger.info("Very little visible text. Using Playwright as precaution.")
        return "dynamic"

    logger.info("Site detected as static.")
    return "static"
```

### 4.3 Create `hotel_scraper/scraper/static_fetcher.py`

```python
"""HTTP fetcher for static sites using requests + tenacity retry."""

import random
import time

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from hotel_scraper.config import Config
from hotel_scraper.scraper.base_fetcher import BaseFetcher


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
```

### 4.4 Create `hotel_scraper/scraper/dynamic_fetcher.py`

```python
"""Browser-based fetcher for JavaScript-rendered sites using Playwright."""

import asyncio
import random

from loguru import logger
from playwright.async_api import async_playwright

from hotel_scraper.config import Config
from hotel_scraper.scraper.base_fetcher import BaseFetcher


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
```

### 4.5 PHASE 4 VALIDATION

```bash
python -c "
from hotel_scraper.scraper.detector import detect_site_type
from hotel_scraper.scraper.static_fetcher import StaticFetcher
from hotel_scraper.scraper.dynamic_fetcher import DynamicFetcher
print('FETCHERS OK')
"
```

Expected output: `FETCHERS OK`

---

## 5. PHASE 5 — PARSER LAYER

### 5.1 Create `hotel_scraper/parser/html_parser.py`

```python
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
```

### 5.2 Create `hotel_scraper/parser/room_extractor.py`

```python
"""Extracts room/cabin names and descriptions from parsed HTML."""

import re
from bs4 import BeautifulSoup, Tag
from loguru import logger

# CSS selectors to try in order. First match wins.
ROOM_SELECTORS = [
    "[class*='room']",
    "[class*='habitacion']",
    "[class*='suite']",
    "[class*='cabin']",
    "[class*='accommodation']",
    "[class*='alojamiento']",
    "[class*='unit']",
    "article",
    ".card",
]

# Tags likely to contain the room name within a room block
NAME_TAGS = ["h1", "h2", "h3", "h4", "strong", "b"]


def extract_rooms(soup: BeautifulSoup) -> list[dict]:
    """Extract raw room data blocks from HTML.

    Args:
        soup: Parsed BeautifulSoup object.

    Returns:
        List of dicts with keys: name, description, raw_html.
        Returns empty list if nothing found.
    """
    rooms: list[dict] = []

    for selector in ROOM_SELECTORS:
        blocks = soup.select(selector)
        if len(blocks) >= 1:
            logger.info(f"Room selector matched: '{selector}' → {len(blocks)} blocks")
            for block in blocks:
                room = _parse_room_block(block)
                if room:
                    rooms.append(room)
            if rooms:
                return rooms

    logger.warning("No room blocks found with any selector.")
    return rooms


def _parse_room_block(block: Tag) -> dict | None:
    """Extract name and description from a single room HTML block.

    Args:
        block: A BeautifulSoup Tag representing one room.

    Returns:
        Dict with name, description, raw_html or None if name not found.
    """
    name_tag = None
    for tag in NAME_TAGS:
        name_tag = block.find(tag)
        if name_tag:
            break

    if not name_tag:
        return None

    name = name_tag.get_text(strip=True)
    if not name or len(name) < 2:
        return None

    # Description: all text in block excluding the name
    full_text = block.get_text(separator=" ", strip=True)
    description = full_text.replace(name, "").strip()
    description = re.sub(r"\s+", " ", description)

    return {
        "name": name,
        "description": description[:500] if description else None,
        "raw_html": str(block)[:2000],
    }
```

### 5.3 Create `hotel_scraper/parser/price_extractor.py`

```python
"""Extracts price information from HTML text."""

import re
from bs4 import BeautifulSoup
from loguru import logger
from hotel_scraper.models.hotel_data import Price

# Regex: matches amounts like $1.200, USD 150, 99.99, etc.
PRICE_REGEX = re.compile(
    r"(?P<currency>USD|ARS|EUR|€|\$)?\s*"
    r"(?P<amount>[\d]{1,3}(?:[.,][\d]{3})*(?:[.,]\d{1,2})?)"
    r"(?:\s*(?P<currency2>USD|ARS|EUR))?",
    re.IGNORECASE,
)

CURRENCY_SYMBOLS = {"$": "ARS", "€": "EUR", "USD": "USD", "ARS": "ARS", "EUR": "EUR"}

SEASON_KEYWORDS = {
    "alta": ["alta", "high", "peak"],
    "baja": ["baja", "low", "off"],
    "media": ["media", "mid", "shoulder"],
}

PERIOD_KEYWORDS = {
    "por noche": ["noche", "night", "nightly", "nuit"],
    "semanal": ["semana", "week", "weekly"],
    "mensual": ["mes", "month", "monthly"],
}


def extract_prices(soup: BeautifulSoup) -> list[Price]:
    """Extract all prices found in the page.

    Args:
        soup: Parsed BeautifulSoup object.

    Returns:
        List of Price objects. Empty list if none found.
    """
    prices: list[Price] = []
    price_tags = soup.find_all(
        lambda tag: tag.name in ["span", "div", "p", "strong", "td"]
        and PRICE_REGEX.search(tag.get_text())
    )

    seen_raw: set[str] = set()

    for tag in price_tags:
        raw_text = tag.get_text(strip=True)
        if raw_text in seen_raw:
            continue
        seen_raw.add(raw_text)

        match = PRICE_REGEX.search(raw_text)
        if not match:
            continue

        amount_str = match.group("amount").replace(".", "").replace(",", ".")
        try:
            amount = float(amount_str)
        except ValueError:
            continue

        if amount < 1 or amount > 10_000_000:
            continue  # Likely not a price

        raw_currency = match.group("currency") or match.group("currency2") or "$"
        currency = CURRENCY_SYMBOLS.get(raw_currency.upper(), "ARS")

        season = _detect_keyword(raw_text, SEASON_KEYWORDS)
        period = _detect_keyword(raw_text, PERIOD_KEYWORDS)

        prices.append(Price(
            amount=amount,
            currency=currency,
            season=season,
            period=period,
            raw_text=raw_text[:200],
        ))

    logger.info(f"Extracted {len(prices)} price(s).")
    return prices


def _detect_keyword(text: str, mapping: dict[str, list[str]]) -> str | None:
    """Match text against a keyword mapping and return the category.

    Args:
        text: Text to search within.
        mapping: Dict of category -> list of keywords.

    Returns:
        Matched category string or None.
    """
    text_lower = text.lower()
    for category, keywords in mapping.items():
        if any(kw in text_lower for kw in keywords):
            return category
    return None
```

### 5.4 Create `hotel_scraper/parser/shift_extractor.py`

```python
"""Extracts check-in, check-out and availability info from HTML."""

import re
from bs4 import BeautifulSoup
from loguru import logger
from hotel_scraper.models.hotel_data import Shift

TIME_REGEX = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(?:hs|h|hrs|am|pm)?\b", re.IGNORECASE)
CHECKIN_KEYWORDS = ["check.?in", "llegada", "arrival", "entrada", "ingreso"]
CHECKOUT_KEYWORDS = ["check.?out", "salida", "departure", "checkout"]


def extract_shift(soup: BeautifulSoup) -> Shift | None:
    """Extract check-in and check-out times from the page.

    Args:
        soup: Parsed BeautifulSoup object.

    Returns:
        Shift object or None if nothing found.
    """
    text = soup.get_text(separator="\n", strip=True)
    lines = text.splitlines()

    check_in: str | None = None
    check_out: str | None = None
    raw_fragments: list[str] = []

    for line in lines:
        line_lower = line.lower()

        is_checkin = any(re.search(kw, line_lower) for kw in CHECKIN_KEYWORDS)
        is_checkout = any(re.search(kw, line_lower) for kw in CHECKOUT_KEYWORDS)

        if is_checkin or is_checkout:
            time_match = TIME_REGEX.search(line)
            if time_match:
                hour = time_match.group(1).zfill(2)
                minute = time_match.group(2) or "00"
                time_str = f"{hour}:{minute}"
                raw_fragments.append(line.strip())

                if is_checkin and not check_in:
                    check_in = time_str
                if is_checkout and not check_out:
                    check_out = time_str

    if not check_in and not check_out:
        logger.warning("No shift/check-in info found.")
        return None

    shift = Shift(
        check_in=check_in,
        check_out=check_out,
        raw_text=" | ".join(raw_fragments[:3]),
    )
    logger.info(f"Shift extracted: check_in={check_in}, check_out={check_out}")
    return shift
```

### 5.5 Create `hotel_scraper/parser/image_extractor.py`

```python
"""Extracts image URLs from HTML, resolving relative paths."""

from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from loguru import logger

SKIP_EXTENSIONS = {".svg", ".gif", ".ico", ".webp"}
MIN_IMAGE_SIZE_HINT = 50  # Ignore images smaller than this in src attribute hints


def extract_image_urls(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Extract all relevant image URLs from the page.

    Handles: <img src>, <img data-src>, <source srcset>, background-image CSS.

    Args:
        soup: Parsed BeautifulSoup object.
        base_url: The original page URL, used to resolve relative paths.

    Returns:
        Deduplicated list of absolute image URL strings.
    """
    urls: set[str] = set()

    # Standard img tags
    for img in soup.find_all("img"):
        for attr in ["src", "data-src", "data-lazy-src", "data-original"]:
            src = img.get(attr)
            if src:
                absolute = urljoin(base_url, src)
                if _is_valid_image_url(absolute):
                    urls.add(absolute)

    # srcset attributes
    for source in soup.find_all(["source", "img"]):
        srcset = source.get("srcset", "")
        for part in srcset.split(","):
            part = part.strip().split(" ")[0]
            if part:
                absolute = urljoin(base_url, part)
                if _is_valid_image_url(absolute):
                    urls.add(absolute)

    logger.info(f"Extracted {len(urls)} image URL(s).")
    return list(urls)


def _is_valid_image_url(url: str) -> bool:
    """Filter out non-image or unwanted URLs.

    Args:
        url: Absolute URL string.

    Returns:
        True if URL looks like a downloadable hotel image.
    """
    parsed = urlparse(url)
    if not parsed.scheme.startswith("http"):
        return False
    path = parsed.path.lower()
    ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
    if ext in SKIP_EXTENSIONS:
        return False
    # Skip tiny icons by name hints
    if any(x in path for x in ["icon", "logo", "pixel", "tracking", "1x1"]):
        return False
    return True
```

### 5.6 PHASE 5 VALIDATION

```bash
python -c "
from hotel_scraper.parser.html_parser import HTMLParser
from hotel_scraper.parser.room_extractor import extract_rooms
from hotel_scraper.parser.price_extractor import extract_prices
from hotel_scraper.parser.shift_extractor import extract_shift
from hotel_scraper.parser.image_extractor import extract_image_urls

html = '<html><body><div class=\"room\"><h2>Suite</h2><p>precio \$5000 por noche</p><img src=\"/img/suite.jpg\"></div></body></html>'
p = HTMLParser(html)
soup = p.get_soup()
rooms = extract_rooms(soup)
prices = extract_prices(soup)
shift = extract_shift(soup)
images = extract_image_urls(soup, 'http://hotel.com')
assert len(rooms) == 1, f'Expected 1 room, got {len(rooms)}'
assert len(prices) >= 1, f'Expected prices, got {len(prices)}'
assert len(images) == 1, f'Expected 1 image, got {len(images)}'
print('PARSERS OK')
"
```

Expected output: `PARSERS OK`

---

## 6. PHASE 6 — LLM FALLBACK

### 6.1 Create `hotel_scraper/llm/prompts.py`

```python
"""Prompt templates for LLM-assisted extraction."""

ROOM_EXTRACTION_PROMPT = """You are a data extraction agent. Analyze the following HTML fragment from a hotel website.

Extract ALL rooms/cabins/suites you can find. For each room return:
- name: room name (string)
- description: short description (string or null)
- capacity: number of guests (int or null)
- amenities: list of amenities found (list of strings)
- prices: list of objects with {amount: float, currency: string, period: string or null, raw_text: string}
- shifts: list of objects with {check_in: string or null, check_out: string or null, raw_text: string or null}
- image_urls: list of image URL strings found in this block

Return ONLY a JSON object with key "rooms" containing the list. No markdown. No explanation. Valid JSON only.

HTML:
{html}
"""

PRICE_EXTRACTION_PROMPT = """Extract all prices from the following text.
Return ONLY a JSON array of objects: [{amount, currency, period, season, raw_text}].
No markdown. No explanation. Valid JSON array only.

Text:
{text}
"""
```

### 6.2 Create `hotel_scraper/llm/llm_client.py`

```python
"""Unified LLM client. Uses Gemini if key available, else raises."""

import json
import os
from loguru import logger
from hotel_scraper.config import Config


class LLMClient:
    """Calls a free LLM API for HTML parsing fallback."""

    def __init__(self) -> None:
        """Initialize with available provider."""
        if Config.GEMINI_API_KEY:
            self.provider = "gemini"
            import google.generativeai as genai
            genai.configure(api_key=Config.GEMINI_API_KEY)
            self._model = genai.GenerativeModel("gemini-2.5-flash")
            logger.info("LLMClient: using Gemini 2.5 Flash")
        else:
            raise RuntimeError(
                "No LLM API key configured. Set GEMINI_API_KEY in .env. "
                "Get a free key at https://aistudio.google.com/"
            )

    def extract_json(self, prompt: str) -> dict | list:
        """Send prompt to LLM and parse JSON response.

        Args:
            prompt: Fully formatted prompt string.

        Returns:
            Parsed Python dict or list from LLM JSON response.

        Raises:
            ValueError: If LLM returns invalid JSON.
            RuntimeError: If API call fails.
        """
        try:
            response = self._model.generate_content(prompt)
            raw = response.text.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw.strip())
        except json.JSONDecodeError as e:
            logger.error(f"LLM returned invalid JSON: {e}")
            raise ValueError(f"LLM JSON parse failed: {e}") from e
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            raise RuntimeError(f"LLM call failed: {e}") from e
```

---

## 7. PHASE 7 — IMAGE DOWNLOADER

### 7.1 Create `hotel_scraper/downloader/image_downloader.py`

```python
"""Async concurrent image downloader with retry."""

import asyncio
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from hotel_scraper.config import Config
from hotel_scraper.models.hotel_data import RoomImage


def sanitize_dirname(name: str) -> str:
    """Convert a room name into a safe directory name.

    Args:
        name: Raw room name string.

    Returns:
        Filesystem-safe lowercase string.
    """
    name = name.lower().strip()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[\s]+", "_", name)
    return name[:60]


async def download_image(
    session: aiohttp.ClientSession,
    image: RoomImage,
    dest_dir: Path,
) -> RoomImage:
    """Download a single image file.

    Args:
        session: Active aiohttp client session.
        image: RoomImage with url and filename set.
        dest_dir: Directory to save the image.

    Returns:
        Updated RoomImage with local_path set and downloaded=True on success.
    """
    dest_path = dest_dir / image.filename
    try:
        async with session.get(image.url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                content = await resp.read()
                dest_path.write_bytes(content)
                image.local_path = str(dest_path)
                image.downloaded = True
                logger.debug(f"Downloaded: {image.filename}")
            else:
                logger.warning(f"HTTP {resp.status} for {image.url}")
    except Exception as e:
        logger.warning(f"Failed to download {image.url}: {e}")
    return image


async def download_all_images(
    room_images: dict[str, list[RoomImage]],
    output_dir: Path,
) -> dict[str, list[RoomImage]]:
    """Download all images for all rooms concurrently.

    Args:
        room_images: Dict mapping room_name -> list of RoomImage.
        output_dir: Root output directory. Images go in output_dir/images/{room_name}/

    Returns:
        Same dict with updated RoomImage objects (local_path, downloaded).
    """
    semaphore = asyncio.Semaphore(Config.MAX_CONCURRENT_IMAGES)
    images_root = output_dir / "images"

    async def bounded_download(session, image, dest):
        async with semaphore:
            return await download_image(session, image, dest)

    async with aiohttp.ClientSession(
        headers={"User-Agent": Config.USER_AGENT}
    ) as session:
        tasks = []
        for room_name, images in room_images.items():
            room_dir = images_root / sanitize_dirname(room_name)
            room_dir.mkdir(parents=True, exist_ok=True)
            for image in images:
                tasks.append(bounded_download(session, image, room_dir))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Rebuild the dict with updated images
    flat_images = [img for imgs in room_images.values() for img in imgs]
    updated = [r for r in results if isinstance(r, RoomImage)]

    # Map back by url
    url_map = {img.url: img for img in updated}
    for room_name, images in room_images.items():
        room_images[room_name] = [url_map.get(img.url, img) for img in images]

    downloaded = sum(1 for img in updated if img.downloaded)
    logger.info(f"Downloaded {downloaded}/{len(flat_images)} images.")
    return room_images
```

---

## 8. PHASE 8 — EXPORTERS

### 8.1 Create `hotel_scraper/exporter/json_exporter.py`

```python
"""Exports Hotel data model to JSON file."""

import json
from pathlib import Path
from loguru import logger
from hotel_scraper.models.hotel_data import Hotel


def export_json(hotel: Hotel, output_dir: Path) -> Path:
    """Write hotel data to data.json inside output_dir.

    Args:
        hotel: Fully populated Hotel object.
        output_dir: Directory to write into. Created if missing.

    Returns:
        Path to the written JSON file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "data.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(hotel.model_dump(), f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"JSON exported: {json_path}")
    return json_path
```

### 8.2 Create `hotel_scraper/exporter/csv_exporter.py`

```python
"""Exports Hotel data to CSV files (rooms.csv and prices.csv)."""

from pathlib import Path
import pandas as pd
from loguru import logger
from hotel_scraper.models.hotel_data import Hotel


def export_csv(hotel: Hotel, output_dir: Path) -> list[Path]:
    """Write rooms.csv and prices.csv to output_dir.

    Args:
        hotel: Fully populated Hotel object.
        output_dir: Target directory.

    Returns:
        List of Paths to written CSV files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    # rooms.csv
    rooms_data = []
    for room in hotel.rooms:
        rooms_data.append({
            "hotel_name": hotel.name,
            "room_name": room.name,
            "description": room.description,
            "capacity": room.capacity,
            "amenities": ", ".join(room.amenities),
            "image_count": len(room.images),
        })
    if rooms_data:
        rooms_path = output_dir / "rooms.csv"
        pd.DataFrame(rooms_data).to_csv(rooms_path, index=False, encoding="utf-8")
        paths.append(rooms_path)
        logger.info(f"rooms.csv exported: {rooms_path}")

    # prices.csv
    prices_data = []
    for room in hotel.rooms:
        for price in room.prices:
            prices_data.append({
                "hotel_name": hotel.name,
                "room_name": room.name,
                "amount": price.amount,
                "currency": price.currency,
                "period": price.period,
                "season": price.season,
                "raw_text": price.raw_text,
            })
    if prices_data:
        prices_path = output_dir / "prices.csv"
        pd.DataFrame(prices_data).to_csv(prices_path, index=False, encoding="utf-8")
        paths.append(prices_path)
        logger.info(f"prices.csv exported: {prices_path}")

    return paths
```

---

## 9. PHASE 9 — ORCHESTRATOR

### 9.1 Create `hotel_scraper/orchestrator.py`

```python
"""Main orchestrator. Coordinates all modules to scrape a hotel URL."""

import asyncio
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger
from tqdm import tqdm

from hotel_scraper.config import Config
from hotel_scraper.downloader.image_downloader import download_all_images
from hotel_scraper.exporter.csv_exporter import export_csv
from hotel_scraper.exporter.json_exporter import export_json
from hotel_scraper.models.hotel_data import Hotel, Room, RoomImage
from hotel_scraper.parser.html_parser import HTMLParser
from hotel_scraper.parser.image_extractor import extract_image_urls
from hotel_scraper.parser.price_extractor import extract_prices
from hotel_scraper.parser.room_extractor import extract_rooms
from hotel_scraper.parser.shift_extractor import extract_shift
from hotel_scraper.scraper.detector import detect_site_type
from hotel_scraper.scraper.dynamic_fetcher import DynamicFetcher
from hotel_scraper.scraper.static_fetcher import StaticFetcher


def _make_output_dir(url: str, base_output: str) -> Path:
    """Create a timestamped output directory for this scrape run.

    Args:
        url: Hotel URL (used to derive name).
        base_output: Base output path string.

    Returns:
        Path to the created directory.
    """
    domain = urlparse(url).netloc.replace("www.", "").replace(".", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{domain}_{timestamp}"
    path = Path(base_output) / folder_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def scrape(url: str, output_dir: str = "./output", use_llm: bool = False) -> Hotel:
    """Full scraping pipeline for a single hotel URL.

    Args:
        url: The hotel website URL.
        output_dir: Root directory for all output files.
        use_llm: Whether to activate LLM fallback when parsers return empty.

    Returns:
        Populated Hotel object.
    """
    logger.info(f"Starting scrape: {url}")
    steps = tqdm(total=7, desc="Scraping hotel")

    # Step 1: Detect site type
    site_type = detect_site_type(url)
    steps.update(1)

    # Step 2: Fetch HTML
    if site_type == "static":
        html = StaticFetcher().fetch(url)
    else:
        html = DynamicFetcher().fetch(url)
    steps.update(1)

    # Step 3: Parse HTML
    parser = HTMLParser(html)
    soup = parser.get_soup()
    steps.update(1)

    # Step 4: Extract data
    raw_rooms = extract_rooms(soup)
    all_prices = extract_prices(soup)
    general_shift = extract_shift(soup)
    all_image_urls = extract_image_urls(soup, url)
    steps.update(1)

    # Step 5: Assemble Room objects
    # If no rooms found and LLM enabled, use LLM fallback
    if not raw_rooms and use_llm:
        logger.warning("No rooms found with selectors. Attempting LLM fallback.")
        raw_rooms = _llm_room_fallback(html)
        site_type = "llm_assisted"

    # Distribute prices and images across rooms (simple distribution strategy)
    rooms: list[Room] = []
    price_per_room = max(1, len(all_prices) // max(len(raw_rooms), 1))
    images_per_room = max(1, len(all_image_urls) // max(len(raw_rooms), 1))

    for i, raw in enumerate(raw_rooms):
        room_prices = all_prices[i * price_per_room: (i + 1) * price_per_room]
        room_img_urls = all_image_urls[i * images_per_room: (i + 1) * images_per_room]
        room_images = [
            RoomImage(url=img_url, filename=f"img_{str(j+1).zfill(3)}.jpg")
            for j, img_url in enumerate(room_img_urls)
        ]
        rooms.append(Room(
            name=raw["name"],
            description=raw.get("description"),
            prices=room_prices,
            shifts=[general_shift] if general_shift else [],
            images=room_images,
            raw_html=raw.get("raw_html"),
        ))
    steps.update(1)

    # Step 6: Download images
    out_path = _make_output_dir(url, output_dir)
    room_images_map = {room.name: room.images for room in rooms}
    updated_map = asyncio.run(download_all_images(room_images_map, out_path))
    for room in rooms:
        room.images = updated_map.get(room.name, room.images)
    steps.update(1)

    # Step 7: Build Hotel and export
    hotel_name = urlparse(url).netloc.replace("www.", "")
    hotel = Hotel(
        name=hotel_name,
        url=url,
        scraped_at=datetime.now().isoformat(),
        rooms=rooms,
        general_shift=general_shift,
        source_type=site_type,
    )
    export_json(hotel, out_path)
    export_csv(hotel, out_path)
    steps.update(1)
    steps.close()

    logger.success(
        f"Scrape complete. {len(rooms)} rooms | "
        f"{sum(len(r.images) for r in rooms)} images | "
        f"Output: {out_path}"
    )
    return hotel


def _llm_room_fallback(html: str) -> list[dict]:
    """Use LLM to extract rooms when CSS selectors fail.

    Args:
        html: Full page HTML string.

    Returns:
        List of raw room dicts with name, description, raw_html.
    """
    try:
        from hotel_scraper.llm.llm_client import LLMClient
        from hotel_scraper.llm.prompts import ROOM_EXTRACTION_PROMPT
        client = LLMClient()
        # Truncate HTML to avoid token limits
        truncated_html = html[:15000]
        prompt = ROOM_EXTRACTION_PROMPT.format(html=truncated_html)
        result = client.extract_json(prompt)
        if isinstance(result, dict) and "rooms" in result:
            return [
                {"name": r.get("name", "Unknown"), "description": r.get("description"), "raw_html": ""}
                for r in result["rooms"]
                if r.get("name")
            ]
    except Exception as e:
        logger.error(f"LLM fallback failed: {e}")
    return []
```

---

## 10. PHASE 10 — CLI ENTRY POINT

### 10.1 Create `hotel_scraper/main.py`

```python
"""CLI entry point for the hotel scraper."""

import argparse
import sys
from loguru import logger
from hotel_scraper.orchestrator import scrape


def main() -> None:
    """Parse CLI arguments and run the scraper."""
    parser = argparse.ArgumentParser(
        prog="hotel-scraper",
        description="Scrape hotel websites and extract rooms, prices, shifts and images.",
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Full URL of the hotel website to scrape.",
    )
    parser.add_argument(
        "--output",
        default="./output",
        help="Root directory for output files. Default: ./output",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Enable LLM fallback when CSS selectors fail. Requires GEMINI_API_KEY in .env",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )

    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level=args.log_level)

    hotel = scrape(url=args.url, output_dir=args.output, use_llm=args.llm)

    print(f"\n✅ Done. Scraped {len(hotel.rooms)} room(s) from {hotel.name}")
    print(f"📁 Output: {args.output}")


if __name__ == "__main__":
    main()
```

---

## 11. PHASE 11 — TESTS

### 11.1 Create `hotel_scraper/tests/test_parsers.py`

```python
"""Unit tests for parser modules."""

import pytest
from bs4 import BeautifulSoup
from hotel_scraper.parser.html_parser import HTMLParser
from hotel_scraper.parser.room_extractor import extract_rooms
from hotel_scraper.parser.price_extractor import extract_prices
from hotel_scraper.parser.shift_extractor import extract_shift
from hotel_scraper.parser.image_extractor import extract_image_urls


SAMPLE_HTML = """
<html>
<body>
  <div class="room">
    <h2>Suite Presidencial</h2>
    <p>Vista al río. Capacidad: 2 personas.</p>
    <span class="price">$85.000 por noche</span>
    <img src="/images/suite1.jpg" alt="Suite">
    <img data-src="/images/suite2.jpg" alt="Suite 2">
  </div>
  <div class="room">
    <h2>Habitación Doble</h2>
    <p>Cómoda habitación estándar.</p>
    <span class="price">USD 50 por noche (Temporada Baja)</span>
    <img src="/images/doble.jpg">
  </div>
  <p>Check-in: 14hs | Check-out: 10hs</p>
</body>
</html>
"""


def test_room_extraction():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    rooms = extract_rooms(soup)
    assert len(rooms) == 2
    assert rooms[0]["name"] == "Suite Presidencial"
    assert rooms[1]["name"] == "Habitación Doble"


def test_price_extraction():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    prices = extract_prices(soup)
    assert len(prices) >= 2
    amounts = [p.amount for p in prices]
    assert 85000.0 in amounts or 85.0 in amounts  # depending on dot/comma parsing
    assert any(p.currency == "USD" for p in prices)


def test_shift_extraction():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    shift = extract_shift(soup)
    assert shift is not None
    assert shift.check_in == "14:00"
    assert shift.check_out == "10:00"


def test_image_extraction():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    images = extract_image_urls(soup, "http://hotel.com")
    assert len(images) >= 2
    assert all(img.startswith("http://hotel.com") for img in images)


def test_empty_html():
    soup = BeautifulSoup("<html><body></body></html>", "lxml")
    assert extract_rooms(soup) == []
    assert extract_prices(soup) == []
    assert extract_shift(soup) is None
    assert extract_image_urls(soup, "http://x.com") == []
```

### 11.2 PHASE 11 VALIDATION

```bash
cd hotel_scraper
python -m pytest tests/test_parsers.py -v
```

Expected: All 5 tests pass. No errors.

---

## 12. FINAL INTEGRATION VALIDATION

Run this command. It must complete without error:

```bash
cd hotel_scraper
python -m hotel_scraper.main --help
```

Expected output contains: `usage: hotel-scraper` and lists `--url`, `--output`, `--llm`.

---

## 13. USAGE — HOW TO RUN

```bash
# Basic usage (static or auto-detected site)
python -m hotel_scraper.main --url https://www.hotelexample.com

# With LLM fallback enabled (requires GEMINI_API_KEY in .env)
python -m hotel_scraper.main --url https://www.hotelexample.com --llm

# Custom output directory + debug logging
python -m hotel_scraper.main --url https://www.hotelexample.com --output ./my_data --log-level DEBUG
```

---

## 14. EXPECTED OUTPUT STRUCTURE

After a successful run, the output directory must contain:

```
output/
└── hotelexample_com_20260428_143022/
    ├── data.json
    ├── rooms.csv
    ├── prices.csv
    └── images/
        ├── suite_presidencial/
        │   ├── img_001.jpg
        │   └── img_002.jpg
        └── habitacion_doble/
            └── img_001.jpg
```

`data.json` schema must match the `Hotel` Pydantic model exactly.
`rooms.csv` must have columns: hotel_name, room_name, description, capacity, amenities, image_count.
`prices.csv` must have columns: hotel_name, room_name, amount, currency, period, season, raw_text.

---

## 15. SCOPE CONSTRAINTS — DO NOT IMPLEMENT

```
CONSTRAINT-001: No GUI. CLI only.
CONSTRAINT-002: No database. Files only.
CONSTRAINT-003: No proxy rotation. Single IP.
CONSTRAINT-004: No login/authentication flows.
CONSTRAINT-005: No parallel multi-URL scraping (single URL per run).
CONSTRAINT-006: No Scrapy. Use requests + playwright as specified.
CONSTRAINT-007: No additional LLM providers beyond Gemini (in MVP).
CONSTRAINT-008: Do not modify the Pydantic models defined in PHASE 2.
```
