"""Extracts image URLs from an HTML block, resolving relative paths."""

from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Tag
from loguru import logger

# Extensions to skip (not room photos)
SKIP_EXTENSIONS = {".svg", ".gif", ".ico"}
# Path fragments that indicate UI/icon images, not room photos
SKIP_PATH_FRAGMENTS = [
    "logo", "icon", "flecha", "arrow", "map-maker",
    "facebook", "instagram", "whatsapp", "footer", "comunes",
    "sprite", "placeholder", "loader",
]


def extract_image_urls(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Extract all relevant image URLs from the page.

    Handles: <img src>, <img data-src>, <source srcset>.
    Filters out UI/icon/logo images.

    Args:
        soup: Parsed BeautifulSoup object.
        base_url: The original page URL, used to resolve relative paths.

    Returns:
        Deduplicated list of absolute image URL strings, ordered by appearance.
    """
    seen: set[str] = set()
    urls: list[str] = []

    for img in soup.find_all("img"):
        for attr in ["src", "data-src", "data-lazy-src", "data-original"]:
            src = img.get(attr, "").strip()
            if src:
                absolute = urljoin(base_url, src)
                if _is_valid_image_url(absolute) and absolute not in seen:
                    seen.add(absolute)
                    urls.append(absolute)

    # srcset attributes
    for source in soup.find_all(["source", "img"]):
        srcset = source.get("srcset", "")
        for part in srcset.split(","):
            part = part.strip().split(" ")[0]
            if part:
                absolute = urljoin(base_url, part)
                if _is_valid_image_url(absolute) and absolute not in seen:
                    seen.add(absolute)
                    urls.append(absolute)

    logger.info(f"Extracted {len(urls)} image URL(s).")
    return urls


def extract_images_from_block(block: Tag, base_url: str) -> list[str]:
    """Extract image URLs from a single room HTML block.

    Args:
        block: A BeautifulSoup Tag representing one room container.
        base_url: Base URL for resolving relative paths.

    Returns:
        List of absolute image URL strings found within this block.
    """
    seen: set[str] = set()
    urls: list[str] = []

    for img in block.find_all("img"):
        for attr in ["src", "data-src", "data-lazy-src", "data-original"]:
            src = img.get(attr, "").strip()
            if src:
                absolute = urljoin(base_url, src)
                if _is_valid_image_url(absolute) and absolute not in seen:
                    seen.add(absolute)
                    urls.append(absolute)

    return urls


def _is_valid_image_url(url: str) -> bool:
    """Filter out non-photo or unwanted URLs."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False

    path_lower = parsed.path.lower()

    if any(path_lower.endswith(ext) for ext in SKIP_EXTENSIONS):
        return False

    if any(frag in path_lower for frag in SKIP_PATH_FRAGMENTS):
        return False

    return True
