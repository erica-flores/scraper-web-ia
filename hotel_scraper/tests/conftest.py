"""Pytest path setup. Allows both `from llm.router import ...` (bare, used by app code)
and `from hotel_scraper.parser.html_parser import ...` (full, used by test_parsers.py).
"""

import sys
from pathlib import Path

_HS_DIR = Path(__file__).parent.parent
_REPO_DIR = _HS_DIR.parent

for p in (str(_HS_DIR), str(_REPO_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)
