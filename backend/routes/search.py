from flask import Blueprint, request, current_app
from backend.database.db import search_all
from backend.utils.helpers import format_response

search_bp = Blueprint("search", __name__, url_prefix="/api")


@search_bp.route("/search", methods=["GET"])
def global_search():
    """
    Search across applicants, documents, filenames, document IDs,
    and extracted identity fields.
    Query param: `q` (string)
    """
    query = request.args.get("q", "").strip()
    if not query:
        return format_response(
            success=True,
            message="Empty search query.",
            data={"applicants": [], "documents": []}
        )

    db_path = current_app.config.get("DATABASE_PATH")
    results = search_all(query=query, limit=12, db_path=db_path)

    return format_response(
        success=True,
        message=f"Search completed with {len(results['applicants'])} applicants and {len(results['documents'])} documents found.",
        data=results
    )
