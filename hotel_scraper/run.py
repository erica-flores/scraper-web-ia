"""Entry point for the Flask web app.

Run with:
    python run.py
"""

import sys
from pathlib import Path

# Ensure the hotel_scraper directory is on sys.path
sys.path.insert(0, str(Path(__file__).parent))

from web.app import create_app

if __name__ == "__main__":
    app = create_app()
    print("Hotel Scraper Web App running at http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
