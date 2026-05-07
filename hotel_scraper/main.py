"""CLI entry point for the hotel scraper."""

import argparse
import sys
from loguru import logger
from orchestrator import scrape


def main() -> None:
    """Parse CLI arguments and run the scraper."""
    parser = argparse.ArgumentParser(
        prog="hotel-scraper",
        description="Scrape hotel websites and extract rooms, prices, shifts and images.",
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Full URL of the hotel website to scrape.",
    )
    parser.add_argument(
        "--output",
        default="./output",
        help="Root directory for output files. Default: ./output",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Enable LLM fallback when CSS selectors fail. Requires GEMINI_API_KEY in .env",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )

    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level=args.log_level)

    hotel = scrape(url=args.url, output_dir=args.output, use_llm=args.llm)

    print(f"\n[SUCCESS] Done. Scraped {len(hotel.rooms)} room(s) from {hotel.name}")
    print(f"[OUTPUT] Output: {args.output}")


if __name__ == "__main__":
    main()
