"""Extracts check-in, check-out and availability info from HTML."""

import re
from bs4 import BeautifulSoup
from loguru import logger
from models.hotel_data import Shift

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
