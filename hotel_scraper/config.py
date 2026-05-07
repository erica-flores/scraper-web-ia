"""Global configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Centralised configuration. Read from .env file."""

    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    DELAY_MIN: float = float(os.getenv("SCRAPER_DELAY_MIN", "1.5"))
    DELAY_MAX: float = float(os.getenv("SCRAPER_DELAY_MAX", "4.0"))
    MAX_CONCURRENT_IMAGES: int = int(os.getenv("MAX_CONCURRENT_IMAGES", "5"))
    TIMEOUT: int = int(os.getenv("SCRAPER_TIMEOUT", "30"))
    MAX_RETRIES: int = int(os.getenv("SCRAPER_MAX_RETRIES", "3"))

    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    DYNAMIC_SIGNALS: list[str] = [
        "__NEXT_DATA__",
        "window.__nuxt__",
        "__REACT_ROUTER__",
        "ng-version",
        "data-reactroot",
        "data-v-app",
    ]
