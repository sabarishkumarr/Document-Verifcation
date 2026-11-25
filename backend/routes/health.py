from flask import Blueprint
from backend.utils.helpers import format_response

health_bp = Blueprint("health", __name__)


@health_bp.route("/api/health", methods=["GET"])
def health_check():
    """
    Health check endpoint to verify backend service status.
    """
    return format_response(
        success=True,
        message="Document Verification API is running"
    )
