"""Shared state TypedDict for the LangGraph scraping pipeline."""

from __future__ import annotations
from typing import Any, Optional
from typing_extensions import TypedDict


class ScraperState(TypedDict, total=False):
    """State passed between all LangGraph nodes."""

    # --- Input ---
    url: str
    output_dir: str
    use_llm: bool

    # --- Detection & Fetching ---
    site_type: Optional[str]        # "static" | "dynamic"
    html: Optional[str]
    soup: Optional[Any]             # BeautifulSoup object

    # --- Extraction (raw) ---
    raw_rooms: list[dict]
    all_prices: list
    general_shift: Optional[Any]
    all_image_urls: list[str]

    # --- LLM navigation ---
    navigated_url: Optional[str]    # URL to which the LLM navigated

    # --- Assembly ---
    rooms: list                     # list[Room] pydantic objects
    out_path: Optional[str]         # absolute path to output folder
    hotel: Optional[Any]            # Hotel pydantic object

    # --- Observability ---
    log_messages: list[str]
    error: Optional[str]
