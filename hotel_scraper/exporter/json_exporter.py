"""Exports Hotel data model to JSON file."""

import json
from pathlib import Path
from loguru import logger
from models.hotel_data import Hotel


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
