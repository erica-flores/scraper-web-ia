"""Flask application factory."""

from pathlib import Path
from flask import Flask
from flask_cors import CORS


def create_app() -> Flask:
    """Create and configure the Flask app."""
    template_dir = Path(__file__).parent / "templates"
    static_dir = Path(__file__).parent / "static"

    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir),
    )
    app.secret_key = "hotel-scraper-secret-2025"

    CORS(app)

    from web.routes import bp
    app.register_blueprint(bp)

    return app
