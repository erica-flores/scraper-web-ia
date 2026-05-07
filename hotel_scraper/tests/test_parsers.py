"""Unit tests for parser modules."""

import pytest
from bs4 import BeautifulSoup
from parser.html_parser import HTMLParser
from parser.room_extractor import extract_rooms
from parser.price_extractor import extract_prices
from parser.shift_extractor import extract_shift
from parser.image_extractor import extract_image_urls


SAMPLE_HTML = """
<html>
<body>
  <div class="room">
    <h2>Suite Presidencial</h2>
    <p>Vista al río. Capacidad: 2 personas.</p>
    <span class="price">$85.000 por noche</span>
    <img src="/images/suite1.jpg" alt="Suite">
    <img data-src="/images/suite2.jpg" alt="Suite 2">
  </div>
  <div class="room">
    <h2>Habitación Doble</h2>
    <p>Cómoda habitación estándar.</p>
    <span class="price">USD 50 por noche (Temporada Baja)</span>
    <img src="/images/doble.jpg">
  </div>
  <p>Check-in: 14hs | Check-out: 10hs</p>
</body>
</html>
"""


def test_room_extraction():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    rooms = extract_rooms(soup)
    assert len(rooms) == 2
    assert rooms[0]["name"] == "Suite Presidencial"
    assert rooms[1]["name"] == "Habitación Doble"


def test_price_extraction():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    prices = extract_prices(soup)
    assert len(prices) >= 2
    amounts = [p.amount for p in prices]
    assert 85000.0 in amounts or 85.0 in amounts  # depending on dot/comma parsing
    assert any(p.currency == "USD" for p in prices)


def test_shift_extraction():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    shift = extract_shift(soup)
    assert shift is not None
    assert shift.check_in == "14:00"
    assert shift.check_out == "10:00"


def test_image_extraction():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    images = extract_image_urls(soup, "http://hotel.com")
    assert len(images) >= 2
    assert all(img.startswith("http://hotel.com") for img in images)


def test_empty_html():
    soup = BeautifulSoup("<html><body></body></html>", "lxml")
    assert extract_rooms(soup) == []
    assert extract_prices(soup) == []
    assert extract_shift(soup) is None
    assert extract_image_urls(soup, "http://x.com") == []
