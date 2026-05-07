"""Detects whether a URL requires static or dynamic fetching."""

import requests
from loguru import logger
from config import Config


def detect_site_type(url: str) -> str:
    """Detect whether the site needs Playwright (dynamic) or requests (static).

    Args:
        url: The hotel website URL.

    Returns:
        "static" or "dynamic"
    """
    try:
        response = requests.get(
            url,
            headers={"User-Agent": Config.USER_AGENT},
            timeout=Config.TIMEOUT,
        )
        html = response.text
    except Exception as e:
        logger.warning(f"Detection request failed: {e}. Defaulting to dynamic.")
        return "dynamic"

    for signal in Config.DYNAMIC_SIGNALS:
        if signal in html:
            logger.info(f"Dynamic signal found: '{signal}'. Using Playwright.")
            return "dynamic"

    # Heuristic: if visible text is very sparse, likely JS-rendered
    import re
    visible_text = re.sub(r"<[^>]+>", "", html)
    visible_text = visible_text.strip()
    if len(visible_text) < 500:
        logger.info("Very little visible text. Using Playwright as precaution.")
        return "dynamic"

    logger.info("Site detected as static.")
    return "static"
