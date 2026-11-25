import os
import sys
from pathlib import Path
from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

# Ensure backend directory is in Python path for direct script executions
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR.parent))

from backend.config import config_by_name
from backend.database.db import init_db
from backend.routes.health import health_bp
from backend.routes.upload import upload_bp
from backend.routes.dashboard import dashboard_bp
from backend.routes.applicants import applicants_bp
from backend.routes.search import search_bp
from backend.routes.demo import demo_bp
from backend.routes.reports import reports_bp


def create_app(config_name: str | None = None) -> Flask:
    """
    Application factory for the VeriDoc-AI Flask backend.
    
    Loads configuration, sets up CORS for React dev server,
    initializes the SQLite database, registers blueprints,
    and installs consistent JSON error handlers.
    """
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    app = Flask(__name__)
    config_obj = config_by_name.get(config_name, config_by_name["default"])
    app.config.from_object(config_obj)

    # 1. Ensure required storage directories exist
    upload_folder = Path(app.config["UPLOAD_FOLDER"])
    processed_folder = Path(app.config["PROCESSED_FOLDER"])
    upload_folder.mkdir(parents=True, exist_ok=True)
    processed_folder.mkdir(parents=True, exist_ok=True)

    # 2. Configure CORS for React + Vite frontend
    # React dev server typically runs on http://localhost:5173 or 127.0.0.1:5173
    CORS(
        app,
        resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*")}},
        supports_credentials=True
    )

    # 3. Initialize SQLite database tables
    db_path = app.config.get("DATABASE_PATH")
    init_db(db_path=db_path)

    # 4. Register API Blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(applicants_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(demo_bp)
    app.register_blueprint(reports_bp)

    # 5. Global JSON error handlers
    @app.errorhandler(400)
    def handle_bad_request(e):
        return jsonify({
            "success": False,
            "message": getattr(e, "description", "Bad Request"),
            "error": "BAD_REQUEST"
        }), 400

    @app.errorhandler(404)
    def handle_not_found(e):
        return jsonify({
            "success": False,
            "message": getattr(e, "description", "The requested resource was not found."),
            "error": "NOT_FOUND"
        }), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(e):
        return jsonify({
            "success": False,
            "message": "The HTTP method is not allowed for this endpoint.",
            "error": "METHOD_NOT_ALLOWED"
        }), 405

    @app.errorhandler(413)
    def handle_file_too_large(e):
        max_mb = app.config.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024) / (1024 * 1024)
        return jsonify({
            "success": False,
            "message": f"File size exceeds the server limit of {max_mb:.1f} MB.",
            "error": "PAYLOAD_TOO_LARGE"
        }), 413

    @app.errorhandler(Exception)
    def handle_generic_exception(e):
        # If it's a known HTTP exception, preserve status code and description
        if isinstance(e, HTTPException):
            return jsonify({
                "success": False,
                "message": e.description,
                "error": e.name.upper().replace(" ", "_")
            }), e.code

        # For unexpected internal errors, avoid exposing internal stack trace
        app.logger.error(f"Unhandled Server Error: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "message": "An internal server error occurred while processing the request.",
            "error": "INTERNAL_SERVER_ERROR"
        }), 500

    return app


# Application instance for WSGI / CLI execution
app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"Starting VeriDoc-AI Backend on http://127.0.0.1:{port}")
    app.run(host=host, port=port, debug=True)
