"""Extracts price information from HTML text."""

import re
from bs4 import BeautifulSoup
from loguru import logger
from models.hotel_data import Price

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
