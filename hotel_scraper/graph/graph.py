"""Builds and compiles the LangGraph scraping pipeline."""

from __future__ import annotations

from langgraph.graph import StateGraph, END

from graph.state import ScraperState
from graph.nodes import (
    node_detect,
    node_fetch,
    node_parse_and_extract,
    node_llm_navigate,
    node_llm_extract,
    node_assemble_rooms,
    node_download_images,
    node_export,
)


# ---------------------------------------------------------------------------
# Routing functions (conditional edges)
# ---------------------------------------------------------------------------

def _should_llm_navigate(state: ScraperState) -> str:
    """After parse: decide whether to navigate with LLM or go straight to assemble.

    Triggers LLM navigation when:
    - No rooms found at all, OR
    - Only 1 room found with no prices AND no images (likely a homepage teaser)
    """
    if not state.get("use_llm"):
        return "assemble_rooms"

    raw_rooms = state.get("raw_rooms", [])

    # No rooms at all
    if not raw_rooms:
        return "llm_navigate"

    # Only 1 room found — check if it looks like a navigation menu item, not a real room
    if len(raw_rooms) == 1:
        room = raw_rooms[0]
        per_room_images = room.get("image_urls", [])
        name = (room.get("name") or "").strip()
        description = (room.get("description") or "").strip()

        # Navigation items typically: short name containing "/" or all-caps menu words,
        # and the "description" is just other nav labels concatenated
        nav_words = {"SUITES", "HABITACIONES", "ROOMS", "PROMOCIONES",
                     "CONTACTO", "FAQ", "UBICACION", "UBICACIÓN"}
        name_upper = name.upper()
        is_nav = (
            "/" in name                        # e.g. "TURNOS / TARIFAS"
            or name_upper in nav_words
            or (not per_room_images and len(description) < 50)
        )
        if is_nav:
            return "llm_navigate"

    return "assemble_rooms"



def _after_llm_navigate(state: ScraperState) -> str:
    """After LLM navigation: if still no rooms and use_llm, try direct extraction."""
    if not state.get("raw_rooms") and state.get("use_llm"):
        return "llm_extract"
    return "assemble_rooms"


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def _build_graph() -> StateGraph:
    g = StateGraph(ScraperState)

    # Register nodes
    g.add_node("detect", node_detect)
    g.add_node("fetch", node_fetch)
    g.add_node("parse_and_extract", node_parse_and_extract)
    g.add_node("llm_navigate", node_llm_navigate)
    g.add_node("llm_extract", node_llm_extract)
    g.add_node("assemble_rooms", node_assemble_rooms)
    g.add_node("download_images", node_download_images)
    g.add_node("export", node_export)

    # Set entry point
    g.set_entry_point("detect")

    # Linear edges
    g.add_edge("detect", "fetch")
    g.add_edge("fetch", "parse_and_extract")

    # After parse: conditional — navigate with LLM or assemble directly
    g.add_conditional_edges(
        "parse_and_extract",
        _should_llm_navigate,
        {
            "llm_navigate": "llm_navigate",
            "assemble_rooms": "assemble_rooms",
        },
    )

    # After LLM navigation: if still no rooms, try direct LLM extraction
    g.add_conditional_edges(
        "llm_navigate",
        _after_llm_navigate,
        {
            "llm_extract": "llm_extract",
            "assemble_rooms": "assemble_rooms",
        },
    )

    # LLM extract always leads to assemble
    g.add_edge("llm_extract", "assemble_rooms")

    # Rest of the pipeline is linear
    g.add_edge("assemble_rooms", "download_images")
    g.add_edge("download_images", "export")
    g.add_edge("export", END)

    return g


# Compile once at module import
_compiled_graph = _build_graph().compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_graph(url: str, output_dir: str = "./output", use_llm: bool = False):
    """Execute the scraping graph and return the Hotel object.

    Args:
        url: Hotel website URL.
        output_dir: Base directory for output files.
        use_llm: Whether to activate LLM navigation/extraction fallbacks.

    Returns:
        Hotel pydantic object populated with scraped data.
    """
    initial_state: ScraperState = {
        "url": url,
        "output_dir": output_dir,
        "use_llm": use_llm,
        "raw_rooms": [],
        "all_prices": [],
        "all_image_urls": [],
        "rooms": [],
        "log_messages": [],
    }

    final_state = _compiled_graph.invoke(initial_state)

    hotel = final_state.get("hotel")
    if hotel is None:
        from models.hotel_data import Hotel
        from urllib.parse import urlparse
        from datetime import datetime
        hotel = Hotel(
            name=urlparse(url).netloc.replace("www.", ""),
            url=url,
            scraped_at=datetime.now().isoformat(),
            rooms=[],
            source_type="error",
        )
    return hotel
