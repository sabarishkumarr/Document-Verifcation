import json
import uuid
import re
from flask import Blueprint, request, current_app, Response
from backend.database.db import (
    list_applicants,
    get_applicant,
    update_applicant,
    insert_applicant,
    get_documents_by_applicant,
    get_audit_reviews,
)
from backend.services.comparator import CrossDocumentComparator
from backend.services.matrix_exporter import export_comparison_matrix_to_xlsx, export_comparison_matrix_to_csv
from backend.utils.helpers import format_response

applicants_bp = Blueprint("applicants", __name__, url_prefix="/api/applicants")


@applicants_bp.route("", methods=["GET"])
def get_applicants():
    """List applicants with associated documents, pending review counts, and optional dataset and status scope."""
    limit = request.args.get("limit", default=100, type=int)
    offset = request.args.get("offset", default=0, type=int)
    dataset = request.args.get("dataset")
    if dataset in ("all", "undefined", "null", ""):
        dataset = None
    status_filter = request.args.get("status")
    if status_filter in ("all", "undefined", "null", ""):
        status_filter = None

    db_path = current_app.config.get("DATABASE_PATH")
    apps = list_applicants(limit=limit, offset=offset, dataset=dataset, status_filter=status_filter, db_path=db_path)
    return format_response(
        success=True,
        message=f"Retrieved {len(apps)} applicants.",
        data={"applicants": apps}
    )


@applicants_bp.route("/<applicant_id>/review", methods=["POST"])
def review_applicant(applicant_id: str):
    """
    Submit an applicant-level KYC review decision:
    - 'verified' (requires zero expired docs, zero critical discrepancies, zero missing mandatory fields)
    - 'requires_attention' / 'manual_review'
    - 'resubmission_requested'
    - 'rejected' (requires recorded reason)
    """
    db_path = current_app.config.get("DATABASE_PATH")
    body = request.get_json(silent=True) or {}
    decision = body.get("decision", "").strip()
    notes = body.get("notes")
    officer_name = body.get("officer_name", "Arjun Mehta (Compliance Officer)")
    document_corrections = body.get("document_corrections")

    from backend.database.db import submit_applicant_review
    try:
        result = submit_applicant_review(
            applicant_id=applicant_id,
            decision=decision,
            notes=notes,
            officer_name=officer_name,
            document_corrections=document_corrections,
            db_path=db_path
        )
        return format_response(
            success=True,
            message=f"Applicant '{applicant_id}' KYC review submitted as '{result['decision']}'.",
            data=result
        )
    except ValueError as ve:
        return format_response(
            success=False,
            message=str(ve),
            status_code=400
        )
    except Exception as e:
        return format_response(
            success=False,
            message=f"Failed to submit applicant review: {str(e)}",
            status_code=500
        )


@applicants_bp.route("", methods=["POST"])
def create_applicant():
    """Create a new applicant profile."""
    body = request.get_json(silent=True) or {}
    applicant_id = body.get("id") or f"APP-{uuid.uuid4().hex[:6].upper()}"
    from backend.database.db import is_placeholder_name
    raw_name = body.get("name")
    name = None if is_placeholder_name(raw_name) else raw_name.strip()
    email = body.get("email")
    phone = body.get("phone")

    db_path = current_app.config.get("DATABASE_PATH")
    insert_applicant(applicant_id=applicant_id, name=name, email=email, phone=phone, db_path=db_path)
    created = get_applicant(applicant_id, db_path=db_path)

    return format_response(
        success=True,
        message=f"Applicant '{applicant_id}' created successfully.",
        data={"applicant": created},
        status_code=201
    )


@applicants_bp.route("/<applicant_id>", methods=["GET"])
def get_applicant_profile(applicant_id: str):
    """
    Retrieve full applicant profile including:
    - All uploaded documents
    - Extracted & parsed fields per document
    - Validation results
    - Cross-document comparison matrix
    """
    db_path = current_app.config.get("DATABASE_PATH")
    applicant = get_applicant(applicant_id, db_path=db_path)
    if not applicant:
        return format_response(
            success=False,
            message=f"Applicant with ID '{applicant_id}' not found.",
            status_code=404
        )

    raw_docs = get_documents_by_applicant(applicant_id, db_path=db_path)
    hydrated_docs = []
    for doc in raw_docs:
        d = dict(doc)
        if d.get("extracted_fields") and isinstance(d["extracted_fields"], str):
            try:
                d["extracted_fields"] = json.loads(d["extracted_fields"])
            except Exception:
                pass
        if d.get("validation_results") and isinstance(d["validation_results"], str):
            try:
                d["validation_results"] = json.loads(d["validation_results"])
            except Exception:
                pass
        hydrated_docs.append(d)

    # Perform cross-document comparison with strict applicant isolation
    cross_comparison = CrossDocumentComparator.compare_applicant_documents(
        hydrated_docs,
        applicant_name=applicant.get("name"),
        applicant_id=applicant_id
    )

    # Harmonize applicant database status with cross-document validation
    from backend.database.db import recompute_applicant_status
    recompute_applicant_status(applicant_id, db_path=db_path)
    applicant = get_applicant(applicant_id, db_path=db_path)

    return format_response(
        success=True,
        message="Applicant profile and verification comparison retrieved.",
        data={
            "applicant": applicant,
            "documents": hydrated_docs,
            "cross_comparison": cross_comparison,
            "comparison_matrix": cross_comparison.get("matrix"),
            "audit_history": get_audit_reviews(applicant_id=applicant_id, db_path=db_path)
        }
    )


@applicants_bp.route("/<applicant_id>/comparison/export", methods=["GET"])
def export_applicant_comparison(applicant_id: str):
    """
    Export applicant cross-document verification matrix as genuine Excel XLSX or CSV.
    """
    db_path = current_app.config.get("DATABASE_PATH")
    export_format = request.args.get("format", "xlsx").lower()

    applicant = get_applicant(applicant_id, db_path=db_path)
    if not applicant:
        return format_response(
            success=False,
            message=f"Applicant with ID '{applicant_id}' not found.",
            status_code=404
        )

    raw_docs = get_documents_by_applicant(applicant_id, db_path=db_path, distinct_types=True)
    hydrated_docs = []
    for doc in raw_docs:
        d = dict(doc)
        if d.get("extracted_fields") and isinstance(d["extracted_fields"], str):
            try:
                d["extracted_fields"] = json.loads(d["extracted_fields"])
            except Exception:
                pass
        if d.get("validation_results") and isinstance(d["validation_results"], str):
            try:
                d["validation_results"] = json.loads(d["validation_results"])
            except Exception:
                pass
        hydrated_docs.append(d)

    cross = CrossDocumentComparator.compare_applicant_documents(
        hydrated_docs,
        applicant_name=applicant.get("name"),
        applicant_id=applicant_id
    )
    matrix = cross.get("matrix") or {}

    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", applicant.get("name", "applicant")).lower()

    if export_format in ("csv", "txt"):
        csv_str = export_comparison_matrix_to_csv(matrix)
        return Response(
            csv_str,
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=verification_matrix_{safe_name}_{applicant_id}.csv"
            }
        )

    # Default: Excel XLSX
    xlsx_bytes = export_comparison_matrix_to_xlsx(matrix)
    return Response(
        xlsx_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=verification_matrix_{safe_name}_{applicant_id}.xlsx"
        }
    )


@applicants_bp.route("/<applicant_id>", methods=["PUT", "PATCH"])
def update_applicant_profile(applicant_id: str):
    """
    Update applicant profile details (name, email, phone, status, risk_level, notes).
    """
    db_path = current_app.config.get("DATABASE_PATH")
    body = request.get_json(silent=True) or {}

    updated = update_applicant(
        applicant_id=applicant_id,
        name=body.get("name"),
        email=body.get("email"),
        phone=body.get("phone"),
        status=body.get("status"),
        risk_level=body.get("risk_level"),
        notes=body.get("notes"),
        db_path=db_path
    )

    if not updated:
        return format_response(
            success=False,
            message=f"Applicant with ID '{applicant_id}' not found.",
            status_code=404
        )

    return format_response(
        success=True,
        message=f"Applicant '{applicant_id}' profile updated successfully.",
        data={"applicant": updated}
    )

