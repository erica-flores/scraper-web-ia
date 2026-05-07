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
