"""Flask application factory."""

from flask import Flask
from pathlib import Path

from quote_manager.models.base import init_db


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.secret_key = "quote-manager-dev-key"

    init_db()

    from quote_manager.web.routes import bp
    app.register_blueprint(bp)

    return app
