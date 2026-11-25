import os
import json
from pathlib import Path
from flask import Blueprint, request, current_app, send_file
from typing import List
from werkzeug.datastructures import FileStorage

from backend.services.file_validator import validate_file
from backend.services.document_processor import DocumentProcessor
from backend.services.text_extractor import is_tesseract_available
from backend.database.db import get_document, list_documents, count_documents, get_audit_reviews
from backend.utils.helpers import format_response

upload_bp = Blueprint("upload", __name__, url_prefix="/api/documents")


def _get_processor() -> DocumentProcessor:
    """Instantiate DocumentProcessor using current Flask application configuration."""
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


@upload_bp.route("/upload", methods=["POST"])
def upload_documents():
    """
    Intake endpoint for KYC documents (Aadhaar, PAN, Passport, Voter ID, Driving Licence).
    
    Accepts single or multi-file multipart/form-data under 'files', 'file', or 'documents'.
    Validates extensions, magic byte signatures, and size thresholds.
    Safely stores documents in storage/uploads/ and persists metadata in SQLite.
    """
    if not request.files:
        return format_response(
            success=False,
            message="No file part in the request. Please provide files via multipart/form-data.",
            status_code=400
        )

    # Collect files from common field keys ('files', 'file', 'documents')
    files: List[FileStorage] = []
    for key in ("files", "file", "documents"):
        files.extend(request.files.getlist(key))

    if not files:
        return format_response(
            success=False,
            message="No files selected for upload.",
            status_code=400
        )

    # Optional applicant identifier from form data
    applicant_id = request.form.get("applicant_id")
    if applicant_id:
        applicant_id = applicant_id.strip()
        if applicant_id.lower() in ("null", "none", "undefined", ""):
            applicant_id = None

    db_path = current_app.config.get("DATABASE_PATH")
    if not applicant_id:
        # Create a provisional applicant record for this batch
        import uuid
        from backend.database.db import insert_applicant
        provisional_id = f"APP-{uuid.uuid4().hex[:6].upper()}"
        insert_applicant(applicant_id=provisional_id, name=None, db_path=db_path)
        applicant_id = provisional_id

    allowed_exts = current_app.config.get("ALLOWED_EXTENSIONS", {"pdf", "jpg", "jpeg", "png"})
    max_size = current_app.config.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)
    processor = _get_processor()

    uploaded_records = []
    validation_errors = []

    for file_storage in files:
        # Check if user submitted an empty form file input without choosing a file
        if not file_storage.filename or file_storage.filename.strip() == "":
            validation_errors.append({
                "filename": "",
                "error": "Empty filename or no file selected."
            })
            continue

        raw_name = file_storage.filename

        # Perform strict validation: extension, non-empty size, and file signature
        is_valid, error_msg, detected_mime = validate_file(
            file_storage=file_storage,
            allowed_extensions=allowed_exts,
            max_size_bytes=max_size
        )

        if not is_valid:
            validation_errors.append({
                "filename": raw_name,
                "error": error_msg
            })
            continue

        try:
            record = processor.save_and_register_document(
                file_storage=file_storage,
                applicant_id=applicant_id,
                mime_type=detected_mime
            )
            uploaded_records.append(record)
        except Exception as e:
            validation_errors.append({
                "filename": raw_name,
                "error": f"Failed to save document: {str(e)}"
            })

    # If every file failed validation
    if not uploaded_records and validation_errors:
        return format_response(
            success=False,
            message="Document upload failed validation.",
            data={"uploaded": [], "errors": validation_errors},
            uploaded=[],
            errors=validation_errors,
            status_code=400
        )

    # Partial or full success
    status_code = 201 if uploaded_records else 200
    msg = f"Successfully uploaded {len(uploaded_records)} document(s)."
    if validation_errors:
        msg += f" {len(validation_errors)} file(s) were rejected."

    return format_response(
        success=True,
        message=msg,
        data={
            "applicant_id": applicant_id,
            "uploaded": uploaded_records,
            "errors": validation_errors
        },
        uploaded=uploaded_records,
        errors=validation_errors,
        status_code=status_code
    )


@upload_bp.route("/<document_id>", methods=["GET"])
def get_document_details(document_id: str):
    """Retrieve metadata and intelligence results of a previously uploaded document."""
    db_path = current_app.config.get("DATABASE_PATH")
    doc = get_document(document_id, db_path=db_path)
    if not doc:
        return format_response(
            success=False,
            message=f"Document with ID '{document_id}' not found.",
            status_code=404
        )
    
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

    return format_response(
        success=True,
        message="Document metadata retrieved.",
        data={"document": d}
    )


@upload_bp.route("/<document_id>/file", methods=["GET"])
def get_document_file(document_id: str):
    """Serve the raw uploaded document binary for inspection."""
    db_path = current_app.config.get("DATABASE_PATH")
    doc = get_document(document_id, db_path=db_path)
    if not doc:
        return format_response(
            success=False,
            message=f"Document with ID '{document_id}' not found.",
            status_code=404
        )

    stored_name = doc.get("stored_filename") or doc.get("original_filename")
    processor = _get_processor()
    file_path = processor.upload_folder / stored_name if stored_name else None

    # Fallback to search fixture directory if not in storage/uploads
    if not file_path or not file_path.exists():
        fixtures_dir = Path(current_app.root_path) / "tests" / "fixtures" / "synthetic_kyc"
        candidates = list(fixtures_dir.rglob(doc.get("original_filename", "")))
        if candidates:
            file_path = candidates[0]

    if not file_path or not file_path.exists():
        return format_response(
            success=False,
            message="Document file not found on disk.",
            status_code=404
        )

    return send_file(
        str(file_path),
        mimetype=doc.get("mime_type") or "application/octet-stream",
        as_attachment=False
    )


@upload_bp.route("", methods=["GET"])
def list_all_documents():
    """List uploaded documents with optional status/type filtering and pagination."""
    limit = request.args.get("limit", default=50, type=int)
    offset = request.args.get("offset", default=0, type=int)
    status_filter = request.args.get("status")
    if status_filter in ("all", "undefined", "null", ""):
        status_filter = None
    doc_type_filter = request.args.get("type")
    if doc_type_filter in ("all", "undefined", "null", ""):
        doc_type_filter = None
    applicant_id = request.args.get("applicant_id")

    db_path = current_app.config.get("DATABASE_PATH")
    total_count = count_documents(
        status_filter=status_filter,
        doc_type_filter=doc_type_filter,
        applicant_id=applicant_id,
        db_path=db_path
    )
    docs = list_documents(
        limit=limit,
        offset=offset,
        status_filter=status_filter,
        doc_type_filter=doc_type_filter,
        applicant_id=applicant_id,
        db_path=db_path
    )
    
    # Hydrate JSON fields for client convenience
    hydrated = []
    for doc in docs:
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
        hydrated.append(d)

    return format_response(
        success=True,
        message=f"Retrieved {len(hydrated)} documents.",
        data={"documents": hydrated, "total_count": total_count, "limit": limit, "offset": offset}
    )


@upload_bp.route("/queue", methods=["GET"])
def get_verification_queue():
    """List documents requiring human verification or officer review."""
    status_filter = request.args.get("status", "pending")
    db_path = current_app.config.get("DATABASE_PATH")
    docs = list_documents(limit=100, offset=0, status_filter=status_filter, db_path=db_path)
    
    hydrated = []
    for doc in docs:
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
        hydrated.append(d)

    return format_response(
        success=True,
        message=f"Retrieved {len(hydrated)} documents in verification queue.",
        data={"queue": hydrated}
    )


@upload_bp.route("/<document_id>/process", methods=["POST"])
def process_document(document_id: str):
    """
    Execute full automated intelligence pipeline:
    1. Extract text (PDF text extraction or OCR fallback)
    2. Classify document type (PAN, Aadhaar, Passport, Voter ID, Driving Licence)
    3. Extract structured KYC fields
    4. Validate ID formats and expiry thresholds
    5. Save results to database and trigger cross-check
    """
    db_path = current_app.config.get("DATABASE_PATH")
    doc = get_document(document_id, db_path=db_path)
    if not doc:
        return format_response(
            success=False,
            message=f"Document with ID '{document_id}' not found.",
            status_code=404
        )

    processor = _get_processor()
    try:
        pipeline_result = processor.process_document_pipeline(document_id)
        return format_response(
            success=True,
            message="Document intelligence pipeline processed successfully.",
            data={"result": pipeline_result}
        )
    except Exception as e:
        return format_response(
            success=False,
            message=f"Pipeline processing failed: {str(e)}",
            status_code=500
        )


@upload_bp.route("/<document_id>/review", methods=["POST"])
def review_document(document_id: str):
    """
    Submit a human verification decision for an extracted document:
    - Decisions: 'approved', 'rejected', 'manual_review'
    - Accepts optional corrected/edited field values
    - Appends entry into audit_reviews ledger
    - Re-evaluates applicant verification status
    """
    body = request.get_json(silent=True) or {}
    decision = body.get("decision", "approved").lower()
    if decision == "resubmission":
        decision = "resubmission_requested"
    if decision not in ("approved", "rejected", "manual_review", "resubmission_requested", "pending"):
        return format_response(
            success=False,
            message="Invalid decision. Must be 'approved', 'rejected', 'manual_review', 'resubmission_requested', or 'pending'.",
            status_code=400
        )

    edited_fields = body.get("edited_fields")
    notes = body.get("notes")
    officer_name = body.get("officer_name", "Arjun Mehta (Review Officer)")

    db_path = current_app.config.get("DATABASE_PATH")
    from backend.database.db import submit_document_review

    try:
        review_result = submit_document_review(
            document_id=document_id,
            decision=decision,
            edited_fields=edited_fields,
            notes=notes,
            officer_name=officer_name,
            db_path=db_path
        )
        return format_response(
            success=True,
            message=f"Document '{document_id}' review submitted as '{decision}'.",
            data={"review": review_result}
        )
    except ValueError as ve:
        return format_response(
            success=False,
            message=str(ve),
            status_code=404
        )
    except Exception as e:
        return format_response(
            success=False,
            message=f"Failed to submit review: {str(e)}",
            status_code=500
        )


@upload_bp.route("/<document_id>/assign", methods=["POST"])
def assign_document(document_id: str):
    """Assign an unassigned document to a confirmed applicant."""
    body = request.get_json(silent=True) or {}
    applicant_id = body.get("applicant_id")
    if not applicant_id:
        return format_response(
            success=False,
            message="applicant_id is required.",
            status_code=400
        )
    db_path = current_app.config.get("DATABASE_PATH")
    from backend.database.db import assign_document_applicant
    success = assign_document_applicant(document_id, applicant_id, db_path=db_path)
    if not success:
        return format_response(
            success=False,
            message="Failed to assign document. Applicant may not exist.",
            status_code=400
        )
    return format_response(
        success=True,
        message=f"Document '{document_id}' successfully assigned to applicant '{applicant_id}'."
    )



@upload_bp.route("/ocr-status", methods=["GET"])
def get_ocr_status():
    """
    Check availability of the native Tesseract OCR engine on the host.
    """
    configured_cmd = current_app.config.get("TESSERACT_CMD")
    available, details = is_tesseract_available(configured_cmd)
    return format_response(
        success=True,
        message="OCR engine status checked.",
        data={
            "tesseract_available": available,
            "details": details
        }
    )


@upload_bp.route("/ai-status", methods=["GET"])
def get_ai_status():
    """
    Check availability, configuration and diagnostic status of the AI Document Intelligence service.
    """
    processor = _get_processor()
    ai_status = processor.ai_extractor.get_status()
    return format_response(
        success=True,
        message="AI document intelligence status checked.",
        data=ai_status
    )


@upload_bp.route("/<document_id>/history", methods=["GET"])
def get_document_history(document_id: str):
    """
    Retrieve audit review ledger and officer verification history for a document.
    """
    db_path = current_app.config.get("DATABASE_PATH")
    doc = get_document(document_id, db_path=db_path)
    if not doc:
        return format_response(
            success=False,
            message=f"Document with ID '{document_id}' not found.",
            status_code=404
        )

    reviews = get_audit_reviews(document_id=document_id, db_path=db_path)
    return format_response(
        success=True,
        message=f"Retrieved {len(reviews)} audit review entries for document '{document_id}'.",
        data={"reviews": reviews}
    )



@upload_bp.route("/<document_id>/extract", methods=["POST"])
def trigger_text_extraction(document_id: str):
    """
    Trigger text extraction for a previously uploaded document.
    
    Supports:
    - Digital PDF page text extraction via PyMuPDF.
    - Scanned PDF page fallback to high-DPI rendering + OCR.
    - JPG, JPEG, and PNG image preprocessing + OCR.
    """
    db_path = current_app.config.get("DATABASE_PATH")
    doc = get_document(document_id, db_path=db_path)
    if not doc:
        return format_response(
            success=False,
            message=f"Document with ID '{document_id}' not found.",
            status_code=404
        )

    processor = _get_processor()
    extraction_result = processor.extract_document_text(document_id)

    status = extraction_result.get("status", "error")
    success = status in ("success", "partial")
    status_code = 200 if success else 422

    msg = "Text extraction completed successfully."
    if status == "partial":
        msg = "Text extraction partially completed with some page warnings."
    elif status == "error":
        msg = f"Text extraction failed: {extraction_result.get('error', 'Unknown extraction error')}"

    return format_response(
        success=success,
        message=msg,
        data={"extraction": extraction_result},
        extraction=extraction_result,
        status_code=status_code
    )


@upload_bp.route("/<document_id>/text", methods=["GET"])
def get_extracted_text(document_id: str):
    """
    Retrieve extracted text and page metadata for an uploaded document.
    """
    db_path = current_app.config.get("DATABASE_PATH")
    doc = get_document(document_id, db_path=db_path)
    if not doc:
        return format_response(
            success=False,
            message=f"Document with ID '{document_id}' not found.",
            status_code=404
        )

    raw_metadata = doc.get("extraction_metadata")
    parsed_metadata = None
    if raw_metadata:
        try:
            parsed_metadata = json.loads(raw_metadata)
        except Exception:
            parsed_metadata = {"raw": raw_metadata}

    return format_response(
        success=True,
        message="Extracted document text retrieved.",
        data={
            "document_id": document_id,
            "filename": doc["original_filename"],
            "processing_status": doc.get("processing_status", "pending"),
            "extracted_text": doc.get("extracted_text", ""),
            "metadata": parsed_metadata
        }
    )

