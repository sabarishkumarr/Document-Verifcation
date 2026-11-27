import os
import json
import uuid
import base64
import hashlib
import logging
from pathlib import Path
from flask import Blueprint, request, jsonify, current_app, g, render_template_string
from typing import List, Dict, Any, Optional
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from backend.api.auth import require_api_key
from backend.services.document_processor import DocumentProcessor
from backend.services.file_validator import validate_file
from backend.services.async_worker import JobManager
from backend.database.db import (
    get_document,
    get_document_extracted_attributes,
    list_document_types,
    insert_document_type,
    submit_document_review,
    recompute_applicant_status,
    create_api_key,
    list_api_keys,
    revoke_api_key,
    create_webhook_subscription,
    list_webhook_subscriptions,
    delete_webhook_subscription,
    is_postgres_configured,
    get_or_create_external_applicant,
    create_batch_submission,
    get_batch_submission,
    update_batch_submission,
    insert_batch_document,
    get_batch_documents,
    get_documents_by_applicant,
    save_applicant_triangulation,
    get_applicant_triangulation,
    get_applicant
)
from backend.services.webhook_dispatcher import WebhookDispatcher
from backend.services.comparator import CrossDocumentComparator
from backend.services.triangulation_rule_service import TriangulationRuleService, get_canonical_combination_key

logger = logging.getLogger(__name__)

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


def get_processor() -> DocumentProcessor:
    """Instantiate shared DocumentProcessor using application configuration."""
    provider = current_app.config.get("AI_PROVIDER", "gemini")
    api_key = (
        current_app.config.get("OPENAI_API_KEY")
        if provider == "openai"
        else current_app.config.get("GEMINI_API_KEY")
    )
    return DocumentProcessor(
        upload_folder=current_app.config.get("UPLOAD_FOLDER"),
        processed_folder=current_app.config.get("PROCESSED_FOLDER"),
        db_path=current_app.config.get("DATABASE_PATH"),
        tesseract_cmd=current_app.config.get("TESSERACT_CMD"),
        enable_pdf_ocr_fallback=current_app.config.get("PDF_OCR_FALLBACK_ENABLED", True),
        min_digital_text_chars=current_app.config.get("PDF_MIN_TEXT_CHARS", 15),
        check_images_for_scan=current_app.config.get("PDF_CHECK_IMAGE_FOR_SCAN", True),
        ocr_dpi=current_app.config.get("OCR_DPI", 300),
        ai_provider=provider,
        ai_api_key=api_key,
        ai_model=current_app.config.get("AI_MODEL"),
        ai_timeout=current_app.config.get("AI_TIMEOUT", 30),
        ai_enabled=current_app.config.get("AI_EXTRACTION_ENABLED", True)
    )


# =========================================================================
# 1. Health & Platform Status
# =========================================================================

@api_v1_bp.route("/health", methods=["GET"])
def health_check():
    """
    Public platform health and configuration endpoint.
    Reports operational readiness, database engine, and AI provider status without exposing secrets.
    """
    processor = get_processor()
    ocr_ready, ocr_msg = processor.extractor.check_ocr_ready()
    ai_status = processor.ai_extractor.get_status()

    return jsonify({
        "status": "healthy",
        "version": "2.0.0",
        "api_version": "v1",
        "database": {
            "engine": "postgresql" if is_postgres_configured() else "sqlite",
            "connected": True
        },
        "services": {
            "ocr": {
                "available": ocr_ready,
                "engine": "tesseract",
                "details": ocr_msg
            },
            "ai": {
                "provider": ai_status.get("provider"),
                "configured": ai_status.get("configured"),
                "model": ai_status.get("model")
            }
        }
    }), 200


@api_v1_bp.route("/ready", methods=["GET"])
def readiness_check():
    """
    Public operational readiness probe for load balancers and upstream gateways.
    Validates database connectivity, OCR engine readiness, and storage permissions.
    """
    db_ok = True
    db_engine = "postgresql" if is_postgres_configured() else "sqlite"
    try:
        from backend.database.db import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        cur.fetchone()
        conn.close()
    except Exception:
        db_ok = False

    processor = get_processor()
    ocr_ready, ocr_msg = processor.extractor.check_ocr_ready()
    
    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    processed_dir = Path(current_app.config["PROCESSED_FOLDER"])
    storage_ok = upload_dir.exists() and os.access(upload_dir, os.W_OK) and processed_dir.exists() and os.access(processed_dir, os.W_OK)

    is_ready = db_ok and storage_ok
    status_code = 200 if is_ready else 503

    return jsonify({
        "status": "ready" if is_ready else "not_ready",
        "ready": is_ready,
        "timestamp": os.getenv("CURRENT_TIME", "2026-11-27T10:00:00Z"),
        "checks": {
            "database": {
                "status": "ok" if db_ok else "fail",
                "connected": db_ok,
                "engine": db_engine
            },
            "ocr": {
                "status": "ok" if ocr_ready else "warn",
                "available": ocr_ready,
                "engine": "tesseract",
                "message": ocr_msg
            },
            "storage": {
                "status": "ok" if storage_ok else "fail",
                "writable": storage_ok,
                "upload_folder": str(upload_dir),
                "processed_folder": str(processed_dir)
            }
        }
    }), status_code


# =========================================================================
# 2. Document Intake & Processing
# =========================================================================

@api_v1_bp.route("/documents", methods=["POST"])
@require_api_key(required_scopes=["documents:write"])
def upload_and_process_document():
    """
    Intake endpoint for document upload and processing.
    Supports asynchronous background processing (default) and synchronous processing (?sync=true).
    """
    if not request.files:
        return jsonify({
            "success": False,
            "error": "BAD_REQUEST",
            "message": "No file uploaded. Provide document file in 'file' multipart field."
        }), 400

    file_obj: Optional[FileStorage] = request.files.get("file") or request.files.get("document")
    if not file_obj:
        file_obj = next(iter(request.files.values()))

    is_valid, err_msg, detected_mime = validate_file(
        file_obj,
        allowed_extensions=current_app.config.get("ALLOWED_EXTENSIONS"),
        max_size_bytes=current_app.config.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)
    )
    if not is_valid:
        return jsonify({
            "success": False,
            "error": "INVALID_FILE",
            "message": err_msg
        }), 400

    applicant_id = request.form.get("applicant_id") or request.args.get("applicant_id")
    sync_mode = str(request.args.get("sync", request.form.get("sync", "false"))).lower() in ("true", "1", "yes")

    processor = get_processor()
    doc_record = processor.save_and_register_document(
        file_storage=file_obj,
        applicant_id=applicant_id,
        mime_type=detected_mime
    )

    document_id = doc_record["id"]
    db_path = current_app.config.get("DATABASE_PATH")

    if sync_mode:
        sync_result = JobManager.process_synchronously(document_id, processor, db_path=db_path)
        job_info = sync_result.get("job") or {}
        pipe_result = sync_result.get("result") or {}

        return jsonify({
            "success": True,
            "mode": "synchronous",
            "document_id": document_id,
            "job_id": job_info.get("id"),
            "status": "completed" if pipe_result else "failed",
            "classification": pipe_result.get("classification"),
            "attributes": pipe_result.get("extracted_fields", {}).get("attributes", []),
            "validation": pipe_result.get("validation"),
            "review_status": doc_record.get("review_status", "pending")
        }), 200

    job = JobManager.submit_job(document_id=document_id, processor=processor, db_path=db_path)

    return jsonify({
        "success": True,
        "mode": "asynchronous",
        "job_id": job["id"],
        "document_id": document_id,
        "status": job.get("status", "queued"),
        "stage": job.get("stage", "intake"),
        "check_status_url": f"/api/v1/jobs/{job['id']}",
        "result_url": f"/api/v1/documents/{document_id}/extraction"
    }), 202


# =========================================================================
# 3. Asynchronous Job Status
# =========================================================================

@api_v1_bp.route("/jobs/<job_id>", methods=["GET"])
@require_api_key(required_scopes=["documents:read"])
def get_job_status(job_id: str):
    """Poll processing status, progress percentage, and pipeline stage for a background job."""
    db_path = current_app.config.get("DATABASE_PATH")
    job = JobManager.get_job_status(job_id, db_path=db_path)
    if not job:
        return jsonify({
            "success": False,
            "error": "NOT_FOUND",
            "message": f"Job with ID '{job_id}' not found."
        }), 404

    return jsonify({
        "success": True,
        "job": job,
        "status": job.get("status") if job else None,
        "progress": job.get("progress") if job else 0,
        "stage": job.get("stage") if job else "",
        "result_summary": job.get("result_summary") if job else None
    }), 200


# =========================================================================
# 4. Document Extraction Results
# =========================================================================

@api_v1_bp.route("/documents/<document_id>/extraction", methods=["GET"])
@api_v1_bp.route("/extraction/<document_id>", methods=["GET"])
@require_api_key(required_scopes=["documents:read"])
def get_document_extraction(document_id: str):
    """Retrieve full classification, attributes with coordinates, and validation results."""
    db_path = current_app.config.get("DATABASE_PATH")
    doc = get_document(document_id, db_path=db_path)
    if not doc:
        return jsonify({
            "success": False,
            "error": "NOT_FOUND",
            "message": f"Document with ID '{document_id}' not found."
        }), 404

    attributes = get_document_extracted_attributes(document_id, db_path=db_path)
    
    extracted_fields = {}
    if doc.get("extracted_fields"):
        if isinstance(doc["extracted_fields"], str):
            try:
                extracted_fields = json.loads(doc["extracted_fields"])
            except Exception:
                extracted_fields = {}
        else:
            extracted_fields = doc["extracted_fields"]

    validation_results = {}
    if doc.get("validation_results"):
        if isinstance(doc["validation_results"], str):
            try:
                validation_results = json.loads(doc["validation_results"])
            except Exception:
                validation_results = {}
        else:
            validation_results = doc["validation_results"]

    return jsonify({
        "success": True,
        "document_id": document_id,
        "applicant_id": doc.get("applicant_id"),
        "filename": doc.get("original_filename"),
        "processing_status": doc.get("processing_status"),
        "review_status": doc.get("review_status"),
        "classification": {
            "classified_type": doc.get("classified_type"),
            "confidence": doc.get("classification_confidence", 0.0),
            "declared_type": doc.get("document_type")
        },
        "attributes": attributes,
        "extracted_fields": extracted_fields,
        "validation": validation_results,
        "reviewed_by": doc.get("reviewed_by"),
        "reviewed_at": doc.get("reviewed_at")
    }), 200


# =========================================================================
# 5. Document Human Review & Status Decisions
# =========================================================================

@api_v1_bp.route("/documents/<document_id>/review", methods=["POST"])
@api_v1_bp.route("/review/<document_id>", methods=["POST"])
@require_api_key(required_scopes=["verification:review"])
def review_document(document_id: str):
    """Submit an officer review decision (approved, rejected, resubmission_requested)."""
    data = request.get_json(silent=True) or {}
    decision = data.get("decision") or data.get("action")
    notes = data.get("notes", "")
    reviewer = data.get("reviewer") or data.get("officer_name") or getattr(g, "api_key_name", "API User")

    if not decision or decision not in ("approved", "rejected", "resubmission_requested"):
        return jsonify({
            "success": False,
            "error": "BAD_REQUEST",
            "message": "Field 'decision' must be one of: 'approved', 'rejected', 'resubmission_requested'."
        }), 400

    db_path = current_app.config.get("DATABASE_PATH")
    doc = get_document(document_id, db_path=db_path)
    if not doc:
        return jsonify({
            "success": False,
            "error": "NOT_FOUND",
            "message": f"Document with ID '{document_id}' not found."
        }), 404

    submit_document_review(
        document_id=document_id,
        decision=decision,
        notes=notes,
        officer_name=reviewer,
        db_path=db_path
    )

    applicant_status = None
    if doc.get("applicant_id"):
        applicant_status = recompute_applicant_status(doc["applicant_id"], db_path=db_path)

    WebhookDispatcher.dispatch_event(
        event_name="document.reviewed",
        payload={
            "document_id": document_id,
            "applicant_id": doc.get("applicant_id"),
            "decision": decision,
            "reviewer": reviewer,
            "notes": notes,
            "applicant_overall_status": applicant_status
        },
        db_path=db_path
    )

    return jsonify({
        "success": True,
        "document_id": document_id,
        "review_status": decision,
        "reviewer": reviewer,
        "applicant_status": applicant_status,
        "message": f"Review decision '{decision}' submitted successfully."
    }), 200


# =========================================================================
# 6. Document Type Catalog
# =========================================================================

@api_v1_bp.route("/document-types", methods=["GET"])
@require_api_key(required_scopes=["documents:read"])
def get_document_types():
    """Retrieve all active registered document types and categories."""
    db_path = current_app.config.get("DATABASE_PATH")
    types = list_document_types(active_only=True, db_path=db_path)
    return jsonify({
        "success": True,
        "total": len(types),
        "document_types": types
    }), 200


@api_v1_bp.route("/document-types", methods=["POST"])
@require_api_key(required_scopes=["admin"])
def register_document_type():
    """Programmatically register a new custom document type definition."""
    data = request.get_json(silent=True) or {}
    type_key = data.get("type_key")
    display_name = data.get("display_name")
    category = data.get("category", "general")
    description = data.get("description", "")

    if not type_key or not display_name:
        return jsonify({
            "success": False,
            "error": "BAD_REQUEST",
            "message": "Both 'type_key' and 'display_name' are required fields."
        }), 400

    clean_key = type_key.strip().lower().replace(" ", "_")
    db_path = current_app.config.get("DATABASE_PATH")

    created = insert_document_type({
        "type_key": clean_key,
        "display_name": display_name.strip(),
        "category": category,
        "description": description,
        "is_system": False,
        "is_active": True
    }, db_path=db_path)

    return jsonify({
        "success": True,
        "document_type": created,
        "message": f"Document type '{clean_key}' registered successfully."
    }), 201


# =========================================================================
# 7. M2M API Key Management
# =========================================================================

@api_v1_bp.route("/auth/keys", methods=["GET"])
@require_api_key(required_scopes=["admin"])
def get_api_keys():
    """List all registered API keys."""
    db_path = current_app.config.get("DATABASE_PATH")
    keys = list_api_keys(db_path=db_path)
    return jsonify({
        "success": True,
        "total": len(keys),
        "api_keys": keys
    }), 200


@api_v1_bp.route("/auth/keys", methods=["POST"])
@require_api_key(required_scopes=["admin"])
def generate_api_key():
    """Generate a new M2M API key."""
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    permissions = data.get("permissions")
    rate_limit_rpm = data.get("rate_limit_rpm", 60)

    if not name:
        return jsonify({
            "success": False,
            "error": "BAD_REQUEST",
            "message": "Field 'name' is required for API key generation."
        }), 400

    db_path = current_app.config.get("DATABASE_PATH")
    raw_key, record = create_api_key(
        name=name,
        permissions=permissions,
        rate_limit_rpm=rate_limit_rpm,
        db_path=db_path
    )

    return jsonify({
        "success": True,
        "api_key": raw_key,
        "key_details": record,
        "key_prefix": record["key_prefix"],
        "name": record["name"],
        "permissions": record["permissions"],
        "rate_limit_rpm": record["rate_limit_rpm"],
        "message": "Store this API key safely now. It will not be shown again."
    }), 201


@api_v1_bp.route("/auth/keys/<int:key_id>", methods=["DELETE"])
@require_api_key(required_scopes=["admin"])
def delete_api_key(key_id: int):
    """Revoke an API key."""
    db_path = current_app.config.get("DATABASE_PATH")
    revoke_api_key(key_id, db_path=db_path)
    return jsonify({
        "success": True,
        "message": f"API key {key_id} has been revoked."
    }), 200


# =========================================================================
# 8. Webhook Subscriptions
# =========================================================================

@api_v1_bp.route("/webhooks", methods=["GET"])
@require_api_key(required_scopes=["admin"])
def get_webhooks():
    """List registered webhook subscriptions."""
    db_path = current_app.config.get("DATABASE_PATH")
    subs = list_webhook_subscriptions(active_only=False, db_path=db_path)
    return jsonify({
        "success": True,
        "total": len(subs),
        "webhooks": subs
    }), 200


@api_v1_bp.route("/webhooks", methods=["POST"])
@require_api_key(required_scopes=["admin"])
def register_webhook():
    """Create an outbound webhook subscription."""
    data = request.get_json(silent=True) or {}
    target_url = data.get("target_url")
    subscribed_events = data.get("subscribed_events")

    if not target_url or not target_url.startswith(("http://", "https://")):
        return jsonify({
            "success": False,
            "error": "BAD_REQUEST",
            "message": "Field 'target_url' must be a valid HTTP or HTTPS URL."
        }), 400

    db_path = current_app.config.get("DATABASE_PATH")
    sub = create_webhook_subscription(
        target_url=target_url,
        subscribed_events=subscribed_events,
        db_path=db_path
    )

    return jsonify({
        "success": True,
        "webhook": sub,
        "subscription": sub,
        "message": "Webhook subscription created successfully. Payloads will be signed with X-VeriDoc-Signature (HMAC-SHA256)."
    }), 201


@api_v1_bp.route("/webhooks/<int:sub_id>", methods=["DELETE"])
@require_api_key(required_scopes=["admin"])
def unregister_webhook(sub_id: int):
    """Delete a webhook subscription."""
    db_path = current_app.config.get("DATABASE_PATH")
    delete_webhook_subscription(sub_id, db_path=db_path)
    return jsonify({
        "success": True,
        "message": f"Webhook subscription {sub_id} deleted."
    }), 200


# =========================================================================
# 9. Schema Versioning & Learning Endpoints
# =========================================================================

@api_v1_bp.route("/schemas/<document_type>/learn", methods=["POST"])
@require_api_key(required_scopes=["admin"])
def learn_document_schema(document_type: str):
    """Learn and increment schema version from verified attributes."""
    from backend.services.schema_learner import SchemaLearner
    db_path = current_app.config.get("DATABASE_PATH")
    try:
        new_schema = SchemaLearner.learn_schema_for_type(type_key=document_type, db_path=db_path)
        return jsonify({
            "success": True,
            "document_type": document_type,
            "schema_version": new_schema["version"],
            "schema": new_schema,
            "attributes_count": len(new_schema.get("attributes", [])),
            "message": f"Schema learned successfully. Promoted to version {new_schema['version']}."
        }), 201
    except ValueError as ve:
        return jsonify({"success": False, "error": "NOT_FOUND", "message": str(ve)}), 404


@api_v1_bp.route("/schemas/<document_type>", methods=["GET"])
@require_api_key(required_scopes=["documents:read"])
def get_document_schema_endpoint(document_type: str):
    """Fetch active schema definition for a document type."""
    from backend.services.schema_learner import SchemaLearner
    db_path = current_app.config.get("DATABASE_PATH")
    schema = SchemaLearner.get_active_schema(type_key=document_type, db_path=db_path)
    if not schema:
        return jsonify({"success": False, "error": "NOT_FOUND", "message": f"Schema for '{document_type}' not found."}), 404
    return jsonify({"success": True, "schema": schema}), 200


@api_v1_bp.route("/schemas/<document_type>/versions", methods=["GET"])
@require_api_key(required_scopes=["documents:read"])
def get_schema_versions_endpoint(document_type: str):
    """List historical schema versions for a document type."""
    from backend.services.schema_learner import SchemaLearner
    db_path = current_app.config.get("DATABASE_PATH")
    versions = SchemaLearner.list_schema_versions(type_key=document_type, db_path=db_path)
    return jsonify({
        "success": True,
        "document_type": document_type,
        "total_versions": len(versions),
        "versions": versions
    }), 200


@api_v1_bp.route("/schemas/<document_type>/rollback", methods=["POST"])
@require_api_key(required_scopes=["admin"])
def rollback_schema_endpoint(document_type: str):
    """Roll back active schema for a document type."""
    from backend.services.schema_learner import SchemaLearner
    data = request.get_json(silent=True) or {}
    target_version = data.get("target_version")
    if not target_version or not isinstance(target_version, int):
        return jsonify({"success": False, "error": "BAD_REQUEST", "message": "Field 'target_version' (integer) is required."}), 400
    db_path = current_app.config.get("DATABASE_PATH")
    success = SchemaLearner.rollback_schema(type_key=document_type, target_version=target_version, db_path=db_path)
    if not success:
        return jsonify({"success": False, "error": "NOT_FOUND", "message": f"Version {target_version} not found."}), 404
    return jsonify({"success": True, "message": f"Schema for '{document_type}' rolled back to active version {target_version}."}), 200


@api_v1_bp.route("/evaluation/benchmark", methods=["GET"])
@require_api_key(required_scopes=["admin"])
def run_dataset_benchmark():
    """Run evaluation benchmark on the authorized 10-person dataset."""
    from backend.services.evaluator import DatasetEvaluator
    db_path = current_app.config.get("DATABASE_PATH")
    benchmark_results = DatasetEvaluator.evaluate_synthetic_dataset(db_path=db_path)
    return jsonify({"success": True, "benchmark": benchmark_results}), 200


# =========================================================================
# 10. Enterprise Bulk Base64 Batch API
# =========================================================================

def _detect_mime_from_bytes(data: bytes, fallback_mime: str = "application/pdf") -> str:
    """Validate magic bytes to ascertain genuine file format."""
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return fallback_mime


@api_v1_bp.route("/batches", methods=["POST"])
@require_api_key(required_scopes=["documents:write"])
def submit_bulk_batch():
    """
    Enterprise batch ingestion endpoint.
    Accepts JSON containing Base64-encoded documents, decodes server-side, validates magic bytes,
    saves directly to disk (never stores Base64 in DB/logs), links to external applicant reference,
    and enqueues asynchronous processing jobs.
    """
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({
            "success": False,
            "error": "BAD_REQUEST",
            "message": "Invalid JSON payload. Body must be a JSON object."
        }), 400

    source_system = data.get("source_system")
    external_applicant_ref = data.get("external_applicant_reference")
    documents = data.get("documents")

    if not source_system or not external_applicant_ref:
        return jsonify({
            "success": False,
            "error": "BAD_REQUEST",
            "message": "Both 'source_system' and 'external_applicant_reference' are required fields."
        }), 400

    if not documents or not isinstance(documents, list) or len(documents) == 0:
        return jsonify({
            "success": False,
            "error": "BAD_REQUEST",
            "message": "Field 'documents' must be a non-empty array of Base64 document objects."
        }), 400

    db_path = current_app.config.get("DATABASE_PATH")

    # Idempotency check
    idempotency_key = data.get("idempotency_key")
    if idempotency_key:
        existing_batch = get_batch_submission(idempotency_key, db_path=db_path)
        if existing_batch:
            docs = get_batch_documents(existing_batch["id"], db_path=db_path)
            return jsonify({
                "success": True,
                "idempotent_replay": True,
                "batch_id": existing_batch["id"],
                "status": existing_batch["status"],
                "applicant_id": existing_batch["applicant_id"],
                "source_system": existing_batch["source_system"],
                "external_applicant_reference": existing_batch["external_applicant_reference"],
                "total_documents": existing_batch["total_documents"],
                "accepted_documents": existing_batch["accepted_documents"],
                "failed_documents": existing_batch["failed_documents"],
                "documents": docs,
                "links": {
                    "status": f"/api/v1/batches/{existing_batch['id']}",
                    "results": f"/api/v1/batches/{existing_batch['id']}/results",
                    "verification": f"/api/v1/batches/{existing_batch['id']}/verification"
                }
            }), 200

    # Resolve or create internal applicant mapping
    applicant_id = get_or_create_external_applicant(
        source_system=source_system.strip(),
        external_applicant_ref=external_applicant_ref.strip(),
        external_application_ref=data.get("external_application_reference"),
        applicant_name=data.get("applicant_name"),
        db_path=db_path
    )

    batch_id = f"BATCH-{uuid.uuid4().hex[:8].upper()}"
    upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
    upload_folder.mkdir(parents=True, exist_ok=True)
    processor = get_processor()

    # Pre-create batch submission record to satisfy foreign key constraints
    create_batch_submission({
        "id": batch_id,
        "source_system": source_system.strip(),
        "external_applicant_reference": external_applicant_ref.strip(),
        "external_application_reference": data.get("external_application_reference"),
        "idempotency_key": idempotency_key,
        "applicant_id": applicant_id,
        "status": "processing",
        "total_documents": len(documents),
        "accepted_documents": 0,
        "failed_documents": 0,
        "verification_status": "pending",
        "results_summary": {}
    }, db_path=db_path)

    accepted_docs = []
    failed_docs = []

    for idx, doc_item in enumerate(documents):
        file_name = doc_item.get("file_name") or f"document_{idx+1}.pdf"
        b64_content = doc_item.get("content_base64")
        ext_doc_ref = doc_item.get("external_document_reference")
        specified_type = doc_item.get("specified_document_type")
        declared_mime = doc_item.get("mime_type", "application/pdf")

        if not b64_content:
            failed_docs.append({
                "file_name": file_name,
                "external_document_reference": ext_doc_ref,
                "error": "Missing 'content_base64' payload"
            })
            insert_batch_document({
                "batch_id": batch_id,
                "file_name": file_name,
                "mime_type": declared_mime,
                "specified_document_type": specified_type,
                "external_document_reference": ext_doc_ref,
                "status": "failed",
                "error_message": "Missing 'content_base64' payload"
            }, db_path=db_path)
            continue

        try:
            # Decode Base64 safely
            # Handle data URI prefixes if present
            if "," in b64_content and "base64" in b64_content[:50]:
                b64_content = b64_content.split(",", 1)[1]

            file_bytes = base64.b64decode(b64_content)
            if len(file_bytes) == 0:
                raise ValueError("Decoded content is empty (0 bytes).")

            # Validate magic bytes
            actual_mime = _detect_mime_from_bytes(file_bytes, declared_mime)
            safe_name = secure_filename(file_name) or f"doc_{idx+1}.bin"
            unique_filename = f"{uuid.uuid4().hex}_{safe_name}"
            saved_path = upload_folder / unique_filename

            # Save decoded file to disk (Never store Base64 in DB/logs)
            with open(saved_path, "wb") as f_out:
                f_out.write(file_bytes)

            file_hash = hashlib.sha256(file_bytes).hexdigest()
            doc_id = f"doc_{uuid.uuid4().hex[:12]}"

            # Insert into documents table
            from backend.database.db import insert_document
            doc_record = insert_document({
                "id": doc_id,
                "applicant_id": applicant_id,
                "original_filename": file_name,
                "stored_filename": unique_filename,
                "file_hash": file_hash,
                "file_size": len(file_bytes),
                "mime_type": actual_mime,
                "document_type": (specified_type or "unknown").lower(),
                "processing_status": "queued",
                "review_status": "pending"
            }, db_path=db_path)

            # Submit background processing job
            job = JobManager.submit_job(document_id=doc_id, processor=processor, db_path=db_path)

            # Insert batch document association
            insert_batch_document({
                "batch_id": batch_id,
                "document_id": doc_id,
                "external_document_reference": ext_doc_ref,
                "file_name": file_name,
                "mime_type": actual_mime,
                "specified_document_type": specified_type,
                "status": "queued",
                "job_id": job["id"]
            }, db_path=db_path)

            accepted_docs.append({
                "document_id": doc_id,
                "external_document_reference": ext_doc_ref,
                "file_name": file_name,
                "mime_type": actual_mime,
                "job_id": job["id"],
                "status": "queued",
                "check_status_url": f"/api/v1/jobs/{job['id']}"
            })

        except Exception as proc_exc:
            err_msg = f"Base64 processing failed: {str(proc_exc)}"
            failed_docs.append({
                "file_name": file_name,
                "external_document_reference": ext_doc_ref,
                "error": err_msg
            })
            insert_batch_document({
                "batch_id": batch_id,
                "file_name": file_name,
                "mime_type": declared_mime,
                "specified_document_type": specified_type,
                "external_document_reference": ext_doc_ref,
                "status": "failed",
                "error_message": err_msg
            }, db_path=db_path)

    batch_status = "processing" if accepted_docs else "failed"
    update_batch_submission(batch_id, {
        "status": batch_status,
        "total_documents": len(documents),
        "accepted_documents": len(accepted_docs),
        "failed_documents": len(failed_docs),
        "results_summary": {"accepted_count": len(accepted_docs), "failed_count": len(failed_docs)}
    }, db_path=db_path)

    return jsonify({
        "success": True,
        "batch_id": batch_id,
        "status": batch_status,
        "applicant_id": applicant_id,
        "source_system": source_system,
        "external_applicant_reference": external_applicant_ref,
        "total_documents": len(documents),
        "accepted_documents": len(accepted_docs),
        "failed_documents": len(failed_docs),
        "documents": accepted_docs,
        "failed": failed_docs,
        "links": {
            "status": f"/api/v1/batches/{batch_id}",
            "results": f"/api/v1/batches/{batch_id}/results",
            "verification": f"/api/v1/batches/{batch_id}/verification"
        }
    }), 202


@api_v1_bp.route("/batches/<batch_id>", methods=["GET"])
@require_api_key(required_scopes=["documents:read"])
def get_batch_status_endpoint(batch_id: str):
    """Retrieve processing progress and status breakdown for a batch submission."""
    db_path = current_app.config.get("DATABASE_PATH")
    batch = get_batch_submission(batch_id, db_path=db_path)
    if not batch:
        return jsonify({
            "success": False,
            "error": "NOT_FOUND",
            "message": f"Batch with ID '{batch_id}' not found."
        }), 404

    docs = get_batch_documents(batch_id, db_path=db_path)
    
    # Calculate live progress
    completed_count = 0
    failed_count = 0
    processing_count = 0

    for d in docs:
        if d.get("document_id"):
            doc_rec = get_document(d["document_id"], db_path=db_path)
            if doc_rec:
                status = doc_rec.get("processing_status", "pending")
                if status == "completed":
                    completed_count += 1
                elif status == "failed":
                    failed_count += 1
                else:
                    processing_count += 1
        else:
            failed_count += 1

    total = batch.get("total_documents") or len(docs)
    current_status = batch.get("status")
    
    # Update status if all completed
    if processing_count == 0 and total > 0 and current_status == "processing":
        new_status = "completed" if failed_count == 0 else ("partial_success" if completed_count > 0 else "failed")
        update_batch_submission(batch_id, {
            "status": new_status,
            "accepted_documents": completed_count,
            "failed_documents": failed_count,
            "completed_at": os.getenv("CURRENT_TIME", "2026-11-27T10:00:00Z")
        }, db_path=db_path)
        batch["status"] = new_status
        batch["accepted_documents"] = completed_count
        batch["failed_documents"] = failed_count

        WebhookDispatcher.dispatch_event(
            event_name="batch.completed",
            payload={
                "batch_id": batch_id,
                "applicant_id": batch.get("applicant_id"),
                "status": new_status,
                "total_documents": total,
                "completed_documents": completed_count,
                "failed_documents": failed_count
            },
            db_path=db_path
        )

    return jsonify({
        "success": True,
        "batch_id": batch_id,
        "status": batch.get("status"),
        "applicant_id": batch.get("applicant_id"),
        "source_system": batch.get("source_system"),
        "external_applicant_reference": batch.get("external_applicant_reference"),
        "total_documents": total,
        "completed_documents": completed_count,
        "processing_documents": processing_count,
        "failed_documents": failed_count,
        "verification_status": batch.get("verification_status", "pending"),
        "created_at": batch.get("created_at"),
        "completed_at": batch.get("completed_at"),
        "links": {
            "results": f"/api/v1/batches/{batch_id}/results",
            "verification": f"/api/v1/batches/{batch_id}/verification"
        }
    }), 200


@api_v1_bp.route("/batches/<batch_id>/results", methods=["GET"])
@require_api_key(required_scopes=["documents:read"])
def get_batch_results(batch_id: str):
    """Retrieve detailed per-document extraction and validation results for all documents in a batch."""
    db_path = current_app.config.get("DATABASE_PATH")
    batch = get_batch_submission(batch_id, db_path=db_path)
    if not batch:
        return jsonify({
            "success": False,
            "error": "NOT_FOUND",
            "message": f"Batch with ID '{batch_id}' not found."
        }), 404

    batch_docs = get_batch_documents(batch_id, db_path=db_path)
    results = []

    for bd in batch_docs:
        doc_id = bd.get("document_id")
        if not doc_id:
            results.append({
                "external_document_reference": bd.get("external_document_reference"),
                "file_name": bd.get("file_name"),
                "status": "failed",
                "error": bd.get("error_message") or "Ingestion failed"
            })
            continue

        doc_rec = get_document(doc_id, db_path=db_path)
        attrs = get_document_extracted_attributes(doc_id, db_path=db_path)
        fields = {}
        if doc_rec and doc_rec.get("extracted_fields"):
            try:
                fields = json.loads(doc_rec["extracted_fields"]) if isinstance(doc_rec["extracted_fields"], str) else doc_rec["extracted_fields"]
            except Exception:
                fields = {}

        results.append({
            "document_id": doc_id,
            "external_document_reference": bd.get("external_document_reference"),
            "file_name": bd.get("file_name"),
            "status": doc_rec.get("processing_status") if doc_rec else "unknown",
            "review_status": doc_rec.get("review_status") if doc_rec else "pending",
            "classified_type": doc_rec.get("classified_type") if doc_rec else "unknown",
            "classification_confidence": doc_rec.get("classification_confidence", 0.0) if doc_rec else 0.0,
            "extracted_attributes": attrs,
            "extracted_fields": fields
        })

    return jsonify({
        "success": True,
        "batch_id": batch_id,
        "applicant_id": batch.get("applicant_id"),
        "total_documents": len(results),
        "results": results
    }), 200


@api_v1_bp.route("/batches/<batch_id>/verification", methods=["POST"])
@require_api_key(required_scopes=["documents:write"])
def trigger_batch_verification(batch_id: str):
    """
    Trigger cross-document verification for the applicant associated with this batch.
    Loads active comparison policy for the present document types, enforces rules,
    and updates batch and applicant triangulation matrices.
    """
    db_path = current_app.config.get("DATABASE_PATH")
    batch = get_batch_submission(batch_id, db_path=db_path)
    if not batch:
        return jsonify({
            "success": False,
            "error": "NOT_FOUND",
            "message": f"Batch with ID '{batch_id}' not found."
        }), 404

    applicant_id = batch.get("applicant_id")
    if not applicant_id:
        return jsonify({
            "success": False,
            "error": "INVALID_STATE",
            "message": "Batch is not linked to an applicant."
        }), 400

    applicant = get_applicant(applicant_id, db_path=db_path)
    docs = get_documents_by_applicant(applicant_id, db_path=db_path)

    hydrated_docs = []
    for d in docs:
        d_copy = dict(d)
        if d_copy.get("extracted_fields") and isinstance(d_copy["extracted_fields"], str):
            try:
                d_copy["extracted_fields"] = json.loads(d_copy["extracted_fields"])
            except Exception:
                pass
        if d_copy.get("validation_results") and isinstance(d_copy["validation_results"], str):
            try:
                d_copy["validation_results"] = json.loads(d_copy["validation_results"])
            except Exception:
                pass
        hydrated_docs.append(d_copy)

    # Execute verification engine with active policy rules
    cross = CrossDocumentComparator.compare_applicant_documents(
        hydrated_docs,
        applicant_name=applicant.get("name") if applicant else None,
        applicant_id=applicant_id
    )

    discrepancies = cross.get("discrepancies") or []
    rule_cfg_id = cross.get("rule_configuration_id")
    rule_ver = cross.get("rule_version", 1)

    # Persist triangulation record
    saved_triang = save_applicant_triangulation(applicant_id, {
        "triangulation_matrix": cross.get("matrix") or {},
        "overall_status": cross.get("overall_verdict") or "VERIFIED",
        "consistency_score": float(cross.get("consistency_score", 100.0)) / 100.0,
        "discrepancy_count": len(discrepancies),
        "discrepancies": discrepancies,
        "rule_configuration_id": rule_cfg_id,
        "rule_version": rule_ver,
        "reviewed_by": getattr(g, "api_key_name", "Enterprise Verification API"),
        "notes": f"Batch {batch_id} verification computed across {len(hydrated_docs)} documents."
    }, db_path=db_path)

    # Update batch submission
    update_batch_submission(batch_id, {
        "verification_status": "completed",
        "rule_configuration_id": rule_cfg_id,
        "rule_version": rule_ver,
        "results_summary": {
            "verdict": cross.get("overall_verdict"),
            "consistency_score": cross.get("consistency_score"),
            "discrepancies": discrepancies
        }
    }, db_path=db_path)

    # Dispatch outbound webhook
    WebhookDispatcher.dispatch_event(
        event_name="verification.completed",
        payload={
            "batch_id": batch_id,
            "applicant_id": applicant_id,
            "overall_verdict": cross.get("overall_verdict"),
            "consistency_score": cross.get("consistency_score"),
            "rule_configuration_id": rule_cfg_id,
            "rule_version": rule_ver,
            "discrepancies": discrepancies
        },
        db_path=db_path
    )

    return jsonify({
        "success": True,
        "batch_id": batch_id,
        "applicant_id": applicant_id,
        "overall_verdict": cross.get("overall_verdict"),
        "consistency_score": cross.get("consistency_score"),
        "rule_configuration_id": rule_cfg_id,
        "rule_version": rule_ver,
        "discrepancies": discrepancies,
        "matrix": cross.get("matrix"),
        "documents_evaluated": cross.get("documents_evaluated")
    }), 200


# =========================================================================
# 11. Applicant Verification Report
# =========================================================================

@api_v1_bp.route("/applicants/<applicant_id>/verification", methods=["GET"])
@require_api_key(required_scopes=["documents:read"])
def get_applicant_verification_report(applicant_id: str):
    """
    Retrieve applicant verification outcomes, comparison matrix, and active rule version info.
    Returns standardized outcomes: MATCH, MISMATCH, MISSING, NOT_COMPARABLE, REVIEW_REQUIRED, NOT_EXECUTED.
    """
    db_path = current_app.config.get("DATABASE_PATH")
    applicant = get_applicant(applicant_id, db_path=db_path)
    if not applicant:
        return jsonify({
            "success": False,
            "error": "NOT_FOUND",
            "message": f"Applicant with ID '{applicant_id}' not found."
        }), 404

    # Check cached or run dynamic comparison
    saved = get_applicant_triangulation(applicant_id, db_path=db_path)
    if not saved:
        docs = get_documents_by_applicant(applicant_id, db_path=db_path)
        hydrated_docs = []
        for d in docs:
            d_copy = dict(d)
            if d_copy.get("extracted_fields") and isinstance(d_copy["extracted_fields"], str):
                try:
                    d_copy["extracted_fields"] = json.loads(d_copy["extracted_fields"])
                except Exception:
                    pass
            hydrated_docs.append(d_copy)

        cross = CrossDocumentComparator.compare_applicant_documents(
            hydrated_docs,
            applicant_name=applicant.get("name"),
            applicant_id=applicant_id
        )

        saved = save_applicant_triangulation(applicant_id, {
            "triangulation_matrix": cross.get("matrix") or {},
            "overall_status": cross.get("overall_verdict") or "VERIFIED",
            "consistency_score": float(cross.get("consistency_score", 100.0)) / 100.0,
            "discrepancy_count": len(cross.get("discrepancies", [])),
            "discrepancies": cross.get("discrepancies") or [],
            "rule_configuration_id": cross.get("rule_configuration_id"),
            "rule_version": cross.get("rule_version", 1),
            "reviewed_by": "System Verification Engine"
        }, db_path=db_path)

    matrix = saved.get("mapped_attributes") or saved.get("triangulation_matrix") or {}
    return jsonify({
        "success": True,
        "applicant_id": applicant_id,
        "applicant_name": applicant.get("name"),
        "overall_verdict": saved.get("triangulation_status") or saved.get("overall_status"),
        "consistency_score": float(saved.get("consistency_score", 1.0)) * (100.0 if saved.get("consistency_score", 1.0) <= 1.0 else 1.0),
        "rule_configuration_id": saved.get("rule_configuration_id"),
        "rule_version": saved.get("rule_version", 1),
        "discrepancies": saved.get("conflicts_detected") or saved.get("discrepancies") or [],
        "matrix": matrix,
        "reviewed_by": saved.get("reviewed_by"),
        "updated_at": saved.get("updated_at")
    }), 200


# =========================================================================
# 12. OpenAPI 3.0 Documentation & Swagger UI
# =========================================================================

SWAGGER_UI_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>VeriDoc AI 2.0 — Enterprise REST API Documentation</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
  <style>
    body { margin: 0; background: #fafafa; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    .topbar { display: none; }
    .swagger-ui .info { margin: 20px 0; }
    .swagger-ui .info .title { font-size: 26px; color: #1e293b; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = () => {
      window.ui = SwaggerUIBundle({
        url: '/api/v1/openapi.json',
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIBundle.SwaggerUIStandalonePreset
        ],
        layout: "BaseLayout"
      });
    };
  </script>
</body>
</html>
"""

@api_v1_bp.route("/docs", methods=["GET"])
def get_swagger_docs():
    """Interactive Swagger UI API Documentation explorer."""
    return render_template_string(SWAGGER_UI_TEMPLATE)


@api_v1_bp.route("/openapi.json", methods=["GET"])
def get_openapi_spec():
    """OpenAPI 3.0.3 specification JSON."""
    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": "VeriDoc AI 2.0 Universal Intelligence & Verification REST API",
            "version": "2.0.0",
            "description": "Enterprise REST API enabling external systems to submit bulk Base64 documents, execute cross-document verification policies, query extracted attributes, and manage webhooks."
        },
        "servers": [
            {"url": "/api/v1", "description": "VeriDoc AI API v1"}
        ],
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key"
                },
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer"
                }
            }
        },
        "security": [
            {"ApiKeyAuth": []},
            {"BearerAuth": []}
        ],
        "paths": {
            "/ready": {
                "get": {
                    "summary": "Operational readiness probe",
                    "description": "Verifies database connectivity, OCR engine readiness, and storage permissions.",
                    "security": [],
                    "responses": {
                        "200": {"description": "Platform is fully operational and ready for traffic"},
                        "503": {"description": "Service unavailable / unhealthy component"}
                    }
                }
            },
            "/batches": {
                "post": {
                    "summary": "Submit a bulk batch of Base64-encoded documents",
                    "description": "Ingests a batch of Base64 documents for an external applicant. Decodes server-side, validates magic bytes, and enqueues background processing.",
                    "responses": {
                        "202": {"description": "Batch accepted for asynchronous intake and extraction"},
                        "400": {"description": "Validation error or invalid Base64 payload"}
                    }
                }
            },
            "/batches/{batch_id}": {
                "get": {
                    "summary": "Get batch processing progress and status",
                    "parameters": [{"name": "batch_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {
                        "200": {"description": "Batch status and document breakdown"}
                    }
                }
            },
            "/batches/{batch_id}/results": {
                "get": {
                    "summary": "Get detailed extraction results for all documents in a batch",
                    "parameters": [{"name": "batch_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {
                        "200": {"description": "Extracted attributes, confidence scores, and flags"}
                    }
                }
            },
            "/batches/{batch_id}/verification": {
                "post": {
                    "summary": "Trigger cross-document verification for a batch",
                    "description": "Enforces active comparison rules for the document types in the batch and produces the verification report.",
                    "parameters": [{"name": "batch_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {
                        "200": {"description": "Cross-document verification results and matrix"}
                    }
                }
            },
            "/applicants/{applicant_id}/verification": {
                "get": {
                    "summary": "Get applicant verification summary and comparison matrix",
                    "parameters": [{"name": "applicant_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {
                        "200": {"description": "Full comparison matrix and policy outcomes"}
                    }
                }
            }
        }
    }
    return jsonify(spec), 200
