"""Extracts room/cabin data from parsed HTML, including per-room images."""

import re
from bs4 import BeautifulSoup, Tag
from loguru import logger

# CSS selectors to try in order — first one that yields valid named rooms wins.
# Covers the full spectrum of hotel room naming in Spanish and English.
ROOM_SELECTORS = [
    # Spanish — most common hotel room class names
    "[class*='habitacion']",
    "[class*='habitaci']",     # handles 'habitación' with encoding variants
    "[class*='cuarto']",
    "[class*='suite']",
    "[class*='departamento']",
    "[class*='depto']",
    "[class*='cabana']",
    "[class*='caba']",         # cabaña, cabañas
    "[class*='alojamiento']",
    "[class*='hospedaje']",
    "[class*='apto']",
    "[class*='apartamento']",
    # English
    "[class*='room']",
    "[class*='cabin']",
    "[class*='bungalow']",
    "[class*='accommodation']",
    "[class*='lodge']",
    "[class*='cottage']",
    "[class*='villa']",
    # Generic patterns often used by hotel CMSs
    "[class*='unit']",
    "[class*='tipo']",         # 'tipo de habitación'
    "[class*='category']",
    "[class*='categoria']",
    "[class*='tarifa']",
    "[class*='plan']",
    # Structural fallbacks (broad — used last)
    "article",
    ".card",
]

# Tags likely to contain the room name within a room block
NAME_TAGS = ["h1", "h2", "h3", "h4", "strong", "b"]

# Minimum character length for a valid room name
MIN_NAME_LEN = 2
# Maximum rooms to return from a single selector to avoid false positives
MAX_ROOMS = 30


def extract_rooms(soup: BeautifulSoup, base_url: str = "") -> list[dict]:
    """Extract raw room data blocks from HTML, including per-room images.

    Args:
        soup: Parsed BeautifulSoup object.
        base_url: Page URL for resolving relative image URLs.

    Returns:
        List of dicts with keys: name, description, raw_html, image_urls.
        Returns empty list if nothing found.
    """
    from parser.image_extractor import extract_images_from_block

    for selector in ROOM_SELECTORS:
        blocks = soup.select(selector)
        if len(blocks) >= 1:
            rooms = []
            for block in blocks[:MAX_ROOMS]:
                room = _parse_room_block(block, base_url)
                if room:
                    rooms.append(room)
            if rooms:
                logger.info(f"Room selector matched: '{selector}' → {len(rooms)} rooms")
                return rooms

    logger.warning("No room blocks found with any selector.")
    return []


def _parse_room_block(block: Tag, base_url: str) -> dict | None:
    """Extract name, description, and images from a single room HTML block.

    Args:
        block: A BeautifulSoup Tag representing one room.
        base_url: For resolving relative image URLs.

    Returns:
        Dict with name, description, raw_html, image_urls — or None if invalid.
    """
    from parser.image_extractor import extract_images_from_block

    # Find name
    name_tag = None
    for tag in NAME_TAGS:
        name_tag = block.find(tag)
        if name_tag:
            break

    if not name_tag:
        return None

    name = name_tag.get_text(strip=True)
    if not name or len(name) < MIN_NAME_LEN:
        return None

    # Description: all text in block, excluding the name heading
    full_text = block.get_text(separator=" ", strip=True)
    description = full_text.replace(name, "", 1).strip()
    description = re.sub(r"\s+", " ", description)

    # Per-room images
    image_urls = extract_images_from_block(block, base_url) if base_url else []

    return {
        "name": name,
        "description": description[:600] if description else None,
        "raw_html": str(block)[:2000],
        "image_urls": image_urls,
    }
