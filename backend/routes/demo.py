from flask import Blueprint, request, current_app
from backend.seed_data import seed_demo_dataset, reset_demo_dataset
from backend.utils.helpers import format_response

demo_bp = Blueprint("demo", __name__, url_prefix="/api/demo")


@demo_bp.route("/seed", methods=["POST"])
def seed_demo():
    """Seed or update the synthetic demonstration dataset idempotently."""
    db_path = current_app.config.get("DATABASE_PATH")
    force = request.args.get("force", "false").lower() == "true"
    result = seed_demo_dataset(db_path=db_path, force_reset=force)
    return format_response(
        success=True,
        message=result["message"],
        data=result
    )


@demo_bp.route("/reset", methods=["POST"])
def reset_demo():
    """Reset the demonstration dataset back to pristine benchmark state."""
    db_path = current_app.config.get("DATABASE_PATH")
    result = reset_demo_dataset(db_path=db_path)
    return format_response(
        success=True,
        message="Demonstration dataset has been reset to its pristine benchmark state.",
        data=result
    )
