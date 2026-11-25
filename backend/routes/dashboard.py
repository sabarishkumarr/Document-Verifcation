from flask import Blueprint, request, current_app
from backend.database.db import get_dashboard_statistics
from backend.utils.helpers import format_response

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


@dashboard_bp.route("/stats", methods=["GET"])
def dashboard_stats():
    """
    Retrieve live operational statistics for the Overview Dashboard.
    Supports ?dataset=all (default), ?dataset=synthetic, or ?dataset=demo.
    """
    db_path = current_app.config.get("DATABASE_PATH")
    dataset = request.args.get("dataset", "all").lower()
    stats = get_dashboard_statistics(db_path=db_path, dataset=dataset)
    return format_response(
        success=True,
        message=f"Dashboard statistics retrieved successfully (scope: {dataset}).",
        data=stats
    )
