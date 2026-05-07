"""Exports Hotel data to CSV files (rooms.csv and prices.csv)."""

from pathlib import Path
import pandas as pd
from loguru import logger
from models.hotel_data import Hotel


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
