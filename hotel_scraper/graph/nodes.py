"""LangGraph nodes. Each function takes ScraperState and returns a partial state update."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin

from loguru import logger

from graph.state import ScraperState

# Module-level LLMClient singleton — reuses the shared router/cache across all nodes.
_llm_singleton = None


def _get_llm_client():
    """Lazy-init a single LLMClient for the whole module."""
    global _llm_singleton
    if _llm_singleton is None:
        from llm.llm_client import LLMClient
        _llm_singleton = LLMClient()
    return _llm_singleton


def _llm_meta_suffix() -> str:
    """Return ' (via provider:model[, cached])' for the latest LLM call, or empty."""
    client = _llm_singleton
    if client is None:
        return ""
    last = client.last_response
    if last is None:
        return ""
    tag = "cached" if last.cached else f"{last.latency_ms}ms"
    return f" (via {last.provider}:{last.model}, {tag})"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(state: ScraperState, msg: str) -> list[str]:
    logger.info(msg)
    return list(state.get("log_messages", [])) + [msg]


def _make_output_dir(url: str, base_output: str) -> Path:
    domain = urlparse(url).netloc.replace("www.", "").replace(".", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(base_output) / f"{domain}_{timestamp}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _fetch_html(url: str, site_type: str) -> str:
    """Fetch HTML using static or dynamic fetcher."""
    from scraper.static_fetcher import StaticFetcher
    from scraper.dynamic_fetcher import DynamicFetcher
    if site_type == "static":
        return StaticFetcher().fetch(url)
    return DynamicFetcher().fetch(url)


def _parse_page(html: str, url: str) -> dict:
    """Parse HTML and extract all data. Returns partial state dict."""
    from parser.html_parser import HTMLParser
    from parser.room_extractor import extract_rooms
    from parser.price_extractor import extract_prices
    from parser.shift_extractor import extract_shift
    from parser.image_extractor import extract_image_urls

    parser = HTMLParser(html)
    soup = parser.get_soup()
    raw_rooms = extract_rooms(soup, base_url=url)
    all_prices = extract_prices(soup)
    general_shift = extract_shift(soup)
    all_image_urls = extract_image_urls(soup, url)

    return {
        "soup": soup,
        "raw_rooms": raw_rooms,
        "all_prices": all_prices,
        "general_shift": general_shift,
        "all_image_urls": all_image_urls,
    }


# ---------------------------------------------------------------------------
# Node 1: Detect site type
# ---------------------------------------------------------------------------

def node_detect(state: ScraperState) -> dict:
    from scraper.detector import detect_site_type
    site_type = detect_site_type(state["url"])
    return {
        "site_type": site_type,
        "log_messages": _log(state, f"[1/7] Site type: {site_type}"),
    }


# ---------------------------------------------------------------------------
# Node 2: Fetch HTML
# ---------------------------------------------------------------------------

def node_fetch(state: ScraperState) -> dict:
    url = state["url"]
    html = _fetch_html(url, state.get("site_type", "static"))
    return {
        "html": html,
        "log_messages": _log(state, f"[2/7] Fetched HTML ({len(html):,} chars)"),
    }


# ---------------------------------------------------------------------------
# Node 3: Parse HTML and extract data
# ---------------------------------------------------------------------------

def node_parse_and_extract(state: ScraperState) -> dict:
    url = state.get("navigated_url") or state["url"]
    parsed = _parse_page(state["html"], url)
    n_rooms = len(parsed["raw_rooms"])
    n_imgs = len(parsed["all_image_urls"])
    n_prices = len(parsed["all_prices"])

    # If CSS selectors found nothing AND LLM is enabled, try to discover
    # the right selector for this specific page before giving up
    if n_rooms == 0 and state.get("use_llm"):
        discovered = _llm_discover_selector(state["html"], url)
        if discovered:
            parsed_retry = _parse_page_with_selector(state["html"], url, discovered)
            if len(parsed_retry["raw_rooms"]) > n_rooms:
                parsed = parsed_retry
                n_rooms = len(parsed["raw_rooms"])
                n_imgs = len(parsed["all_image_urls"])
                n_prices = len(parsed["all_prices"])
                return {
                    **parsed,
                    "log_messages": _log(
                        state,
                        f"[3/7] LLM selector '{discovered}': {n_rooms} rooms, {n_prices} prices, {n_imgs} images"
                    ),
                }

    return {
        **parsed,
        "log_messages": _log(
            state,
            f"[3/7] CSS parse: {n_rooms} rooms, {n_prices} prices, {n_imgs} images"
        ),

    }


# ---------------------------------------------------------------------------
# Node 4a: LLM autonomous navigation
# ---------------------------------------------------------------------------

def node_llm_navigate(state: ScraperState) -> dict:
    from llm.prompts import LINK_NAVIGATION_PROMPT

    soup = state["soup"]
    base_url = state["url"]
    site_type = state.get("site_type", "static")

    # Collect all meaningful links (include hash/anchor links for SPAs)
    links = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a["href"]
        if href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        if text:  # only include links with visible text
            links.append(f"- Text: '{text}', URL: '{href}'")

    if not links:
        return {"log_messages": _log(state, "[4/7] LLM navigate: no links found.")}

    links_str = "\n".join(links[:60])

    try:
        client = _get_llm_client()
        prompt = LINK_NAVIGATION_PROMPT.format(links=links_str)
        result = client.extract_json_quick(prompt)

        chosen_href = result.get("next_url") if isinstance(result, dict) else None
        reason = result.get("reason", "") if isinstance(result, dict) else ""

        if chosen_href:
            # Resolve to absolute URL — handles both relative paths and anchors
            next_url = urljoin(base_url, chosen_href)
            logs = _log(state, f"[4/7] LLM → '{chosen_href}' ({reason}){_llm_meta_suffix()}")

            html = _fetch_html(next_url, site_type)
            parsed = _parse_page(html, next_url)
            n_rooms = len(parsed["raw_rooms"])
            n_imgs = len(parsed["all_image_urls"])

            return {
                **parsed,
                "navigated_url": next_url,
                "html": html,
                "log_messages": logs + [
                    f"After navigation: {n_rooms} rooms, {n_imgs} images"
                ],
            }
    except Exception as e:
        logger.error(f"LLM navigation failed: {e}")

    return {"log_messages": _log(state, "[4/7] LLM navigation: no suitable link found.")}


# ---------------------------------------------------------------------------
# Node 4b: LLM direct extraction from HTML
# ---------------------------------------------------------------------------

def node_llm_extract(state: ScraperState) -> dict:
    from llm.prompts import ROOM_EXTRACTION_PROMPT

    html = state.get("html", "")
    base_url = state.get("navigated_url") or state["url"]
    truncated = html[:18000]

    try:
        client = _get_llm_client()
        prompt = ROOM_EXTRACTION_PROMPT.format(html=truncated, base_url=base_url)
        result = client.extract_json(prompt)

        rooms_list = []
        if isinstance(result, dict) and "rooms" in result:
            rooms_list = result["rooms"]
        elif isinstance(result, list):
            rooms_list = result

        raw_rooms = []
        for r in rooms_list:
            if not isinstance(r, dict) or not r.get("name"):
                continue
            raw_rooms.append({
                "name": r["name"],
                "description": r.get("description"),
                "raw_html": "",
                "image_urls": r.get("image_urls", []),
                # also pass prices/amenities from LLM for later assembly
                "_llm_prices": r.get("prices", []),
                "_llm_amenities": r.get("amenities", []),
                "_llm_capacity": r.get("capacity"),
            })

        return {
            "raw_rooms": raw_rooms,
            "log_messages": _log(state, f"[4b/7] LLM extract: {len(raw_rooms)} rooms{_llm_meta_suffix()}"),
        }
    except Exception as e:
        logger.error(f"LLM extract failed: {e}")
        return {"raw_rooms": [], "log_messages": _log(state, f"[4b/7] LLM extract failed: {e}")}


# ---------------------------------------------------------------------------
# Node 5: Assemble Room objects
# ---------------------------------------------------------------------------

def node_assemble_rooms(state: ScraperState) -> dict:
    from models.hotel_data import Room, RoomImage, Price
    from parser.price_extractor import extract_prices
    from parser.html_parser import HTMLParser

    raw_rooms = state.get("raw_rooms", [])
    all_prices = state.get("all_prices", [])
    all_image_urls = state.get("all_image_urls", [])
    general_shift = state.get("general_shift")

    rooms = []
    for i, raw in enumerate(raw_rooms):
        # ---- Images: prefer per-room images over global pool ----
        room_img_urls: list[str] = raw.get("image_urls", [])

        # If no per-room images, fall back to global pool (distributed evenly)
        if not room_img_urls and all_image_urls:
            n = max(len(raw_rooms), 1)
            chunk = max(1, len(all_image_urls) // n)
            room_img_urls = all_image_urls[i * chunk: (i + 1) * chunk]

        room_images = [
            RoomImage(url=img_url, filename=f"img_{str(j + 1).zfill(3)}.jpg")
            for j, img_url in enumerate(room_img_urls)
        ]

        # ---- Prices: prefer LLM-extracted prices, then global pool ----
        llm_prices_raw = raw.get("_llm_prices", [])
        if llm_prices_raw:
            room_prices = []
            for p in llm_prices_raw:
                try:
                    amount = float(p.get("amount", 0))
                    if amount > 0:
                        room_prices.append(Price(
                            amount=amount,
                            currency=p.get("currency", "ARS"),
                            period=p.get("period"),
                            raw_text=p.get("raw_text", ""),
                        ))
                except (ValueError, TypeError):
                    pass
        else:
            # Distribute global prices evenly
            n = max(len(raw_rooms), 1)
            chunk = max(1, len(all_prices) // n)
            room_prices = all_prices[i * chunk: (i + 1) * chunk]

        rooms.append(Room(
            name=raw["name"],
            description=raw.get("description"),
            capacity=raw.get("_llm_capacity"),
            amenities=raw.get("_llm_amenities", []),
            prices=room_prices,
            shifts=[general_shift] if general_shift else [],
            images=room_images,
            raw_html=raw.get("raw_html"),
        ))

    return {
        "rooms": rooms,
        "log_messages": _log(state, f"[5/7] Assembled {len(rooms)} rooms"),
    }


# ---------------------------------------------------------------------------
# Node 6: Download images
# ---------------------------------------------------------------------------

def node_download_images(state: ScraperState) -> dict:
    from downloader.image_downloader import download_all_images

    rooms = state.get("rooms", [])
    url = state["url"]
    output_dir = state.get("output_dir", "./output")
    out_path = _make_output_dir(url, output_dir)

    room_images_map = {room.name: room.images for room in rooms}
    updated_map = asyncio.run(download_all_images(room_images_map, out_path))

    for room in rooms:
        room.images = updated_map.get(room.name, room.images)

    total_imgs = sum(len(r.images) for r in rooms)
    return {
        "rooms": rooms,
        "out_path": str(out_path),
        "log_messages": _log(state, f"[6/7] Downloaded {total_imgs} images → {out_path}"),
    }


# ---------------------------------------------------------------------------
# Node 7: Export JSON + CSV
# ---------------------------------------------------------------------------

def node_export(state: ScraperState) -> dict:
    from exporter.json_exporter import export_json
    from exporter.csv_exporter import export_csv
    from models.hotel_data import Hotel

    rooms = state.get("rooms", [])
    url = state["url"]
    out_path = Path(state["out_path"])
    general_shift = state.get("general_shift")
    navigated = state.get("navigated_url")

    source_type = "llm_assisted" if navigated else state.get("site_type", "static")
    hotel_name = urlparse(url).netloc.replace("www.", "")

    hotel = Hotel(
        name=hotel_name,
        url=url,
        scraped_at=datetime.now().isoformat(),
        rooms=rooms,
        general_shift=general_shift,
        source_type=source_type,
    )

    export_json(hotel, out_path)
    export_csv(hotel, out_path)

    return {
        "hotel": hotel,
        "log_messages": _log(state, f"[7/7] Done. {len(rooms)} rooms → {out_path}"),
    }


# ---------------------------------------------------------------------------
# Helper: LLM-based CSS selector discovery
# ---------------------------------------------------------------------------

def _llm_discover_selector(html: str, url: str) -> str | None:
    """Ask the LLM to identify the CSS selector for room blocks on this page.

    Called when all fixed selectors in ROOM_SELECTORS return nothing.
    Returns a CSS selector string, or None if the LLM can't find one.
    """
    from llm.prompts import ROOM_SELECTOR_DISCOVERY_PROMPT

    try:
        client = _get_llm_client()
        prompt = ROOM_SELECTOR_DISCOVERY_PROMPT.format(html=html[:8000])
        result = client.extract_json_quick(prompt)

        if isinstance(result, dict):
            selector = result.get("selector")
            confidence = result.get("confidence", 0)
            reason = result.get("reason", "")
            if selector and confidence >= 40:
                logger.info(
                    f"LLM discovered selector: '{selector}' "
                    f"(confidence={confidence}, reason={reason})"
                )
                return selector
            else:
                logger.info(
                    f"LLM selector discovery: low confidence ({confidence}). {reason}"
                )
    except Exception as e:
        logger.warning(f"LLM selector discovery failed: {e}")

    return None


def _parse_page_with_selector(html: str, url: str, extra_selector: str) -> dict:
    """Re-parse the page using an LLM-discovered selector in addition to fixed ones.

    Temporarily prepends the discovered selector to ROOM_SELECTORS so it's
    tried first, without permanently modifying the module-level list.
    """
    from parser.html_parser import HTMLParser
    from parser.room_extractor import extract_rooms, ROOM_SELECTORS
    from parser.price_extractor import extract_prices
    from parser.shift_extractor import extract_shift
    from parser.image_extractor import extract_image_urls
    import parser.room_extractor as room_mod

    original_selectors = room_mod.ROOM_SELECTORS[:]
    try:
        # Inject the discovered selector at position 0
        room_mod.ROOM_SELECTORS = [extra_selector] + original_selectors

        parser_obj = HTMLParser(html)
        soup = parser_obj.get_soup()
        raw_rooms = extract_rooms(soup, base_url=url)
        all_prices = extract_prices(soup)
        general_shift = extract_shift(soup)
        all_image_urls = extract_image_urls(soup, url)

        return {
            "soup": soup,
            "raw_rooms": raw_rooms,
            "all_prices": all_prices,
            "general_shift": general_shift,
            "all_image_urls": all_image_urls,
        }
    finally:
        # Always restore original selectors
        room_mod.ROOM_SELECTORS = original_selectors
