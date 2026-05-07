"""Prompt templates for LLM-assisted extraction."""

ROOM_EXTRACTION_PROMPT = """You are a data extraction agent. Analyze the following HTML fragment from a hotel website.
The base URL of this page is: {base_url}

Extract ALL lodging units you can find. These may be called: rooms, suites, cabins, apartments, bungalows, cottages,
habitaciones, cuartos, suites, departamentos, cabañas, bungalows, villas, estudios, apto, or ANY other accommodation name.

For each unit return:
- name: room/unit name (string)
- description: short description (string or null)
- capacity: number of guests (int or null)
- amenities: list of amenities found (list of strings)
- prices: list of objects with {{amount: float, currency: string, period: string or null, raw_text: string}}
- shifts: list of objects with {{check_in: string or null, check_out: string or null, raw_text: string or null}}
- image_urls: list of ABSOLUTE image URLs found specifically for this unit. Resolve relative URLs using the base URL above.

IMPORTANT:
- Be inclusive: if it looks like an accommodation type offered by the hotel, include it.
- Only include image_urls that are actual room photos (not logos, icons, arrows, or generic decorations).
- Only include prices that are actual tariffs (ARS/USD amounts). Do NOT include phone numbers or address numbers as prices.
- If a price text mentions a tariff (e.g. "$ 49000" or "USD 80") extract the numeric amount only.

Return ONLY a JSON object with key "rooms" containing the list. No markdown. No explanation. Valid JSON only.

HTML:
{html}
"""

PRICE_EXTRACTION_PROMPT = """Extract all TARIFF prices from the following text from a hotel website.
Only include actual room prices (ARS or USD amounts). Do NOT include phone numbers, street numbers, or sizes.

Return ONLY a JSON array of objects: [{{amount: float, currency: string, period: string or null, season: string or null, raw_text: string}}].
No markdown. No explanation. Valid JSON array only.

Text:
{text}
"""

LINK_NAVIGATION_PROMPT = """You are an autonomous web scraper agent. Your goal is to find the page on this hotel website
that lists the types of accommodations (rooms, suites, cabins, apartments, etc.) along with their tariffs or descriptions.

Given the following navigation links found on the current page, choose the BEST link to navigate to.

Look for links whose text (in any language) suggests accommodation types or pricing:
- Spanish: Habitaciones, Cuartos, Suites, Cabañas, Departamentos, Alojamiento, Hospedaje, Tarifas, Turnos, Tipos de alojamiento, Acomodaciones, Ver más, Conocé nuestras habitaciones
- English: Rooms, Suites, Cabins, Accommodation, Lodging, Rates, Tariffs, Our Rooms, Book, Stay
- Also consider: any link that sounds like it would list multiple room types with prices

Links:
{links}

Return ONLY a JSON object with:
- "next_url": the href value of the chosen link EXACTLY as it appears above (do not modify it, do not add domain)
- "reason": one sentence explaining why this link is the best choice

If absolutely no suitable link is found, return {{"next_url": null, "reason": "no suitable link found"}}.
No markdown. No explanation outside the JSON. Valid JSON only.
"""

ROOM_SELECTOR_DISCOVERY_PROMPT = """You are a web scraping expert. Analyze the following HTML structure of a hotel website page.

Your task: identify the CSS selector that best targets the individual accommodation blocks (rooms, suites, cabins, etc.).
Each block typically contains: a room name heading, a description, a price, and possibly an image.

Return ONLY a JSON object with:
- "selector": the CSS selector string (e.g. ".room-item", "[class*='suite']", "article.card")
- "confidence": integer 0-100
- "reason": brief explanation

If you cannot identify a reliable selector, return {{"selector": null, "confidence": 0, "reason": "..."}}.
No markdown. No explanation outside the JSON. Valid JSON only.

HTML (first 8000 chars):
{html}
"""
