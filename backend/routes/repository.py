"""
VeriDoc AI 2.0 — Document Repository & Dynamic Schema Management Routes
"""

import os
import re
import json
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from flask import Blueprint, request, current_app, jsonify
from werkzeug.datastructures import FileStorage

from backend.database.db import (
    get_db_connection,
    list_document_types,
    get_document_type,
    get_document_type_details,
    insert_document_type,
    insert_document,
    update_document_type_definition,
    get_repository_stats,
    publish_document_schema,
    rollback_document_schema,
    get_document_schema,
)
from backend.services.schema_learner import SchemaLearner
from backend.services.classifier import DocumentClassifier
from backend.routes.upload import validate_file, sanitize_filename, _get_processor, _resolve_doc_file_path

logger = logging.getLogger(__name__)

repository_bp = Blueprint("repository_bp", __name__, url_prefix="/api/repository")


def format_resp(success: bool, message: str, data: Any = None, status_code: int = 200):
    return jsonify({
        "success": success,
        "message": message,
        "data": data
    }), status_code


@repository_bp.route("/stats", methods=["GET"])
def repository_stats():
    """Retrieve aggregate statistics for the Document Repository."""
    try:
        db_path = current_app.config.get("DATABASE_PATH")
        stats = get_repository_stats(db_path=db_path)
        return format_resp(True, "Repository statistics retrieved.", stats)
    except Exception as e:
        logger.error(f"Error fetching repository stats: {e}")
        return format_resp(False, f"Failed to retrieve repository statistics: {str(e)}", status_code=500)


@repository_bp.route("/types", methods=["GET"])
def get_types():
    """
    List all cataloged document types with optional filters:
    - category: filter by category slug (or 'all')
    - source_origin: filter by 'system', 'ai_discovered', 'employee_created' (or 'all')
    - search: search query
    - active_only: boolean (default: false to show complete catalogue)
    """
    try:
        db_path = current_app.config.get("DATABASE_PATH")
        category = request.args.get("category")
        origin = request.args.get("source_origin") or request.args.get("origin")
        search = request.args.get("search") or request.args.get("q")
        active_only = request.args.get("active_only", "false").lower() in ("true", "1")

        types_list = list_document_types(
            active_only=active_only,
            category=category,
            source_origin=origin,
            search=search,
            include_stats=True,
            db_path=db_path
        )
        return format_resp(True, f"Retrieved {len(types_list)} document type(s).", {
            "types": types_list,
            "total_count": len(types_list)
        })
    except Exception as e:
        logger.error(f"Error listing document types: {e}")
        return format_resp(False, f"Failed to list document types: {str(e)}", status_code=500)


@repository_bp.route("/types", methods=["POST"])
def create_type():
    """
    Register a new document type in the repository.
    Supports either manual definition or AI-discovered initial attributes.
    """
    try:
        db_path = current_app.config.get("DATABASE_PATH")
        payload = request.get_json(silent=True) or {}

        raw_key = payload.get("type_key") or payload.get("id") or ""
        display_name = payload.get("display_name") or payload.get("name") or ""
        category = payload.get("category", "general")
        description = payload.get("description", "")
        origin = payload.get("source_origin", "employee_created")
        icon = payload.get("icon", "file-text")
        tags = payload.get("tags", [])
        attr_defs = payload.get("attribute_definitions") or payload.get("attributes") or []

        # Validate slug
        clean_key = re.sub(r"[^a-z0-9_]", "_", raw_key.lower().strip()).strip("_")
        if not clean_key or len(clean_key) < 2:
            return format_resp(False, "Invalid type_key. Must be at least 2 alphanumeric characters or underscores.", status_code=400)
        if not display_name or len(display_name.strip()) < 2:
            return format_resp(False, "Display name is required.", status_code=400)

        # Check existing
        existing = get_document_type(clean_key, db_path=db_path)
        if existing:
            return format_resp(False, f"Document type '{clean_key}' is already registered.", status_code=409)

        # Normalize attribute definitions
        normalized_attrs = []
        for a in attr_defs:
            if not isinstance(a, dict):
                continue
            ak = re.sub(r"[^a-z0-9_]", "_", str(a.get("attribute_key") or a.get("key") or "").lower().strip()).strip("_")
            if not ak:
                continue
            normalized_attrs.append({
                "attribute_key": ak,
                "display_label": a.get("display_label") or a.get("label") or ak.replace("_", " ").title(),
                "data_type": a.get("data_type", "string"),
                "required": bool(a.get("required", False)),
                "description": a.get("description", ""),
                "validation_rule": a.get("validation_rule") or a.get("regex_pattern") or "",
                "extraction_guidance": a.get("extraction_guidance") or a.get("anchor_phrase") or "",
                "confidence_threshold": float(a.get("confidence_threshold") or 0.70),
                "is_active": bool(a.get("is_active", True))
            })

        # Insert definition
        type_entry = {
            "type_key": clean_key,
            "display_name": display_name.strip(),
            "category": category.strip().lower(),
            "description": description.strip(),
            "is_system": False,
            "is_active": True,
            "source_origin": origin,
            "icon": icon,
            "tags": tags if isinstance(tags, list) else []
        }
        saved_type = insert_document_type(type_entry, db_path=db_path)

        # Synthesize Schema v1
        sample_text = payload.get("sample_text", "")
        schema_res = SchemaLearner.create_initial_schema(
            type_key=clean_key,
            display_name=display_name.strip(),
            attribute_definitions=normalized_attrs,
            sample_text=sample_text,
            db_path=db_path
        )

        full_details = get_document_type_details(clean_key, db_path=db_path)
        return format_resp(True, f"Document type '{display_name}' successfully registered.", full_details, status_code=201)

    except Exception as e:
        logger.error(f"Error creating document type: {e}")
        return format_resp(False, f"Failed to register document type: {str(e)}", status_code=500)


@repository_bp.route("/types/<id_or_key>", methods=["GET"])
def get_type_details(id_or_key: str):
    """Fetch complete details, schemas, and attributes for a document type."""
    try:
        db_path = current_app.config.get("DATABASE_PATH")
        details = get_document_type_details(id_or_key, db_path=db_path)
        if not details:
            return format_resp(False, f"Document type '{id_or_key}' not found.", status_code=404)
        return format_resp(True, "Document type details retrieved.", details)
    except Exception as e:
        logger.error(f"Error fetching document type {id_or_key}: {e}")
        return format_resp(False, f"Failed to retrieve document type: {str(e)}", status_code=500)


@repository_bp.route("/types/<id_or_key>", methods=["PUT"])
def update_type(id_or_key: str):
    """Update document type metadata, description, category, or active status."""
    try:
        db_path = current_app.config.get("DATABASE_PATH")
        doc_type = get_document_type(id_or_key, db_path=db_path)
        if not doc_type:
            return format_resp(False, f"Document type '{id_or_key}' not found.", status_code=404)

        payload = request.get_json(silent=True) or {}
        updates = {}
        for k in ("display_name", "category", "description", "is_active", "icon", "tags", "source_origin"):
            if k in payload:
                updates[k] = payload[k]

        if updates:
            update_document_type_definition(doc_type["id"], updates, db_path=db_path)

        details = get_document_type_details(doc_type["id"], db_path=db_path)
        return format_resp(True, f"Document type '{doc_type['display_name']}' updated.", details)
    except Exception as e:
        logger.error(f"Error updating document type {id_or_key}: {e}")
        return format_resp(False, f"Failed to update document type: {str(e)}", status_code=500)


@repository_bp.route("/types/<id_or_key>/schemas", methods=["POST"])
@repository_bp.route("/types/<id_or_key>/schema/publish", methods=["POST"])
def publish_schema(id_or_key: str):
    """
    Publish a new schema version for a document type.
    Increments version, saves attribute definitions, and preserves prior history.
    """
    try:
        db_path = current_app.config.get("DATABASE_PATH")
        doc_type = get_document_type(id_or_key, db_path=db_path)
        if not doc_type:
            return format_resp(False, f"Document type '{id_or_key}' not found.", status_code=404)

        payload = request.get_json(silent=True) or {}
        attrs = payload.get("attribute_definitions") or payload.get("attributes") or []
        if not attrs:
            return format_resp(False, "attribute_definitions is required and must not be empty.", status_code=400)

        # Normalize attributes
        normalized_attrs = []
        for a in attrs:
            if not isinstance(a, dict):
                continue
            ak = re.sub(r"[^a-z0-9_]", "_", str(a.get("attribute_key") or a.get("key") or "").lower().strip()).strip("_")
            if not ak:
                continue
            normalized_attrs.append({
                "attribute_key": ak,
                "display_label": a.get("display_label") or a.get("label") or ak.replace("_", " ").title(),
                "data_type": a.get("data_type", "string"),
                "required": bool(a.get("required", False)),
                "description": a.get("description", ""),
                "validation_rule": a.get("validation_rule") or a.get("regex_pattern") or "",
                "extraction_guidance": a.get("extraction_guidance") or a.get("anchor_phrase") or "",
                "confidence_threshold": float(a.get("confidence_threshold") or 0.70),
                "is_active": bool(a.get("is_active", True))
            })

        schema_payload = {
            "schema_name": payload.get("schema_name", f"{doc_type['display_name']} Schema Update"),
            "attribute_definitions": normalized_attrs,
            "spatial_templates": payload.get("spatial_templates", {}),
            "sample_count": payload.get("sample_count", 0)
        }

        pub_res = publish_document_schema(doc_type["id"], schema_payload, db_path=db_path)
        full_details = get_document_type_details(doc_type["id"], db_path=db_path)
        return format_resp(True, f"Schema Version {pub_res['version']} published successfully.", full_details, status_code=201)

    except Exception as e:
        logger.error(f"Error publishing schema for {id_or_key}: {e}")
        return format_resp(False, f"Failed to publish schema: {str(e)}", status_code=500)


@repository_bp.route("/types/<id_or_key>/rollback", methods=["POST"])
def rollback_schema(id_or_key: str):
    """Roll back the active schema for a document type to a specified target version."""
    try:
        db_path = current_app.config.get("DATABASE_PATH")
        doc_type = get_document_type(id_or_key, db_path=db_path)
        if not doc_type:
            return format_resp(False, f"Document type '{id_or_key}' not found.", status_code=404)

        payload = request.get_json(silent=True) or {}
        target_version = payload.get("target_version")
        if not target_version:
            return format_resp(False, "target_version is required for rollback.", status_code=400)

        ok = rollback_document_schema(doc_type["id"], int(target_version), db_path=db_path)
        if not ok:
            return format_resp(False, f"Could not roll back to Version {target_version}. Version may not exist.", status_code=400)

        full_details = get_document_type_details(doc_type["id"], db_path=db_path)
        return format_resp(True, f"Document type rolled back to Schema Version {target_version}.", full_details)

    except Exception as e:
        logger.error(f"Error rolling back schema for {id_or_key}: {e}")
        return format_resp(False, f"Failed to roll back schema: {str(e)}", status_code=500)


@repository_bp.route("/discover-attributes", methods=["POST"])
def discover_attributes_from_samples():
    """
    Accept representative sample files, extract text and spatial layout,
    and discover candidate attributes and suggested data types.
    """
    try:
        db_path = current_app.config.get("DATABASE_PATH")
        files = request.files.getlist("files") or request.files.getlist("file")
        if not files:
            return format_resp(False, "No sample files provided for attribute discovery.", status_code=400)

        from backend.routes.upload import _get_processor
        processor = _get_processor()
        allowed_exts = current_app.config.get("ALLOWED_EXTENSIONS", {"pdf", "jpg", "jpeg", "png"})
        max_size = current_app.config.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)

        temp_dir = Path(current_app.config.get("UPLOAD_FOLDER", "storage/uploads")) / "temp_discovery"
        temp_dir.mkdir(parents=True, exist_ok=True)

        all_discovered = []
        sample_names = []
        primary_text = ""
        seen_keys = set()
        classification_result = {"classified_type": "unknown", "confidence": 0.0}

        for fs in files:
            if not fs.filename:
                continue
            sample_names.append(fs.filename)
            is_valid, err_msg, mime = validate_file(fs, allowed_exts, max_size)
            if not is_valid:
                continue

            temp_path = temp_dir / f"disc_{uuid.uuid4().hex[:8]}_{sanitize_filename(fs.filename)}"
            fs.seek(0)
            fs.save(str(temp_path))

            try:
                ext_res = processor.extractor.extract_from_file(temp_path, original_filename=fs.filename)
                text = ext_res.get("full_text", "")
                tokens = ext_res.get("spatial_tokens", [])
                if not primary_text:
                    primary_text = text

                cls_out = DocumentClassifier.classify(text, db_path=db_path)
                if cls_out.get("confidence", 0) > classification_result.get("confidence", 0):
                    classification_result = cls_out

                discovered = SchemaLearner.discover_attributes_from_sample(text, spatial_tokens=tokens)
                for d in discovered:
                    k = d.get("attribute_key")
                    if k and k not in seen_keys:
                        all_discovered.append(d)
                        seen_keys.add(k)
            finally:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass

        pred_type = classification_result.get("classified_type", "unknown")
        conf = classification_result.get("confidence", 0.0)

        return format_resp(True, f"Discovered {len(all_discovered)} attribute(s) from sample(s).", {
            "predicted_type": pred_type,
            "confidence": conf,
            "display_name": classification_result.get("display_name", pred_type.replace("_", " ").title()),
            "category": classification_result.get("category", "general"),
            "sample_filenames": sample_names,
            "sample_text_preview": primary_text[:600] if primary_text else "",
            "discovered_attributes": all_discovered
        })

    except Exception as e:
        logger.error(f"Error in sample attribute discovery: {e}")
        return format_resp(False, f"Failed to discover attributes from sample: {str(e)}", status_code=500)


@repository_bp.route("/types/<id_or_key>/sample", methods=["GET"])
def get_type_sample_document(id_or_key: str):
    """
    Retrieve an existing database document as a specimen for interactive attribute mapping.
    Queries the PostgreSQL documents table for documents belonging to this document type,
    selecting the most complete, verified specimen with valid preview files and extracted attributes.
    Preserves strict applicant isolation and never returns unrelated documents.
    """
    try:
        db_path = current_app.config.get("DATABASE_PATH")
        doc_type = get_document_type(id_or_key, db_path=db_path)
        if not doc_type:
            return format_resp(False, f"Document type '{id_or_key}' not found.", status_code=404)

        type_key = doc_type["type_key"]
        
        # Build search aliases
        search_keys = [type_key]
        if type_key == "salary_slip":
            search_keys.append("payslip")
        elif type_key == "payslip":
            search_keys.append("salary_slip")
        elif type_key == "driving_licence":
            search_keys.extend(["dl", "driving_license"])
        elif type_key == "voter_id":
            search_keys.extend(["voterid", "epic"])
        elif type_key == "commercial_invoice":
            search_keys.append("invoice")
        elif type_key == "bank_statement":
            search_keys.append("statement")
        elif type_key == "tax_form_16":
            search_keys.extend(["form_16", "form16"])
        elif type_key == "utility_bill":
            search_keys.extend(["electricity_bill", "utility"])

        conds = " OR ".join(["document_type = ? OR classified_type = ? OR LOWER(original_filename) LIKE ?" for _ in search_keys])
        params = []
        for sk in search_keys:
            params.extend([sk, sk, f"%{sk.lower()}%"])

        conn = get_db_connection(db_path)
        cur = conn.cursor()
        cur.execute(f"""
            SELECT id, applicant_id, original_filename, stored_filename, document_type, 
                   classified_type, processing_status, file_size, mime_type,
                   extracted_text, extracted_fields, extraction_metadata
            FROM documents 
            WHERE processing_status = 'completed' AND ({conds})
        """, tuple(params))
        candidates = [dict(r) for r in cur.fetchall()]
        conn.close()

        processor = _get_processor()
        scored_candidates = []
        for c in candidates:
            fp = _resolve_doc_file_path(c, processor)
            if not fp or not fp.exists():
                continue

            score = 100 # Base score for file existing on disk
            fields = c.get("extracted_fields")
            if isinstance(fields, str):
                try:
                    fields = json.loads(fields)
                except Exception:
                    fields = {}
            if isinstance(fields, dict):
                attrs = fields.get("attributes")
                if attrs and isinstance(attrs, list):
                    score += 100
                    if any(a.get("bounding_box") for a in attrs):
                        score += 150
                if any(fields.get(f) for f in ["applicant_name", "name", "dob", "date_of_birth", "id_number", "identification_number", "employee_name", "gross_earnings"]):
                    score += 50

            meta = c.get("extraction_metadata")
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            if isinstance(meta, dict) and meta.get("spatial_tokens"):
                score += 50

            orig = (c.get("original_filename") or "").lower()
            doc_id = str(c.get("id") or "")
            if "synthetic" in orig or "demo" in orig or doc_id.startswith("DOC-SYN-") or doc_id.startswith("DOC-DEMO-"):
                score += 50
            if c.get("document_type") == type_key:
                score += 30

            scored_candidates.append((c, score))

        best_doc = max(scored_candidates, key=lambda x: x[1])[0] if scored_candidates else None
        details = get_document_type_details(doc_type["id"], db_path=db_path)

        return format_resp(True, "Specimen document resolved for interactive mapping." if best_doc else f"No specimen document found for '{type_key}' in database.", {
            "document_type": doc_type,
            "sample_document_id": best_doc["id"] if best_doc else None,
            "sample_filename": best_doc["original_filename"] if best_doc else None,
            "has_specimen": best_doc is not None,
            "is_synthetic": True,
            "sample_label": best_doc["original_filename"] if best_doc else "NO SPECIMEN IN DATABASE",
            "details": details
        })
    except Exception as e:
        logger.error(f"Error fetching sample document for {id_or_key}: {e}")
        return format_resp(False, f"Failed to retrieve sample document: {str(e)}", status_code=500)


@repository_bp.route("/types/<id_or_key>/sample", methods=["POST"])
def upload_type_sample_document(id_or_key: str):
    """
    Fallback upload: allows uploading a specimen document directly when none exists in database.
    """
    try:
        db_path = current_app.config.get("DATABASE_PATH")
        doc_type = get_document_type(id_or_key, db_path=db_path)
        if not doc_type:
            return format_resp(False, f"Document type '{id_or_key}' not found.", status_code=404)

        if "file" not in request.files:
            return format_resp(False, "No file uploaded in 'file' field.", status_code=400)

        file = request.files["file"]
        if not file or not file.filename:
            return format_resp(False, "Empty filename.", status_code=400)

        allowed_exts = current_app.config.get("ALLOWED_EXTENSIONS", {"pdf", "jpg", "jpeg", "png"})
        max_size = current_app.config.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)
        is_valid, err_msg, mime = validate_file(file, allowed_exts, max_size)
        if not is_valid:
            return format_resp(False, err_msg, status_code=400)

        processor = _get_processor()
        safe_name = sanitize_filename(file.filename)
        doc_id = f"SPECIMEN-{uuid.uuid4().hex[:12].upper()}"
        stored_name = f"specimen_{uuid.uuid4().hex[:8]}_{safe_name}"
        dest_path = processor.upload_folder / stored_name
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        file.seek(0)
        file.save(str(dest_path))

        # Perform extraction
        ext_res = processor.extractor.extract_from_file(dest_path, original_filename=safe_name)
        text = ext_res.get("full_text", "")
        tokens = ext_res.get("spatial_tokens", [])

        # Discover initial attributes
        discovered = SchemaLearner.discover_attributes_from_sample(text, spatial_tokens=tokens)

        # Store in documents table
        type_key = doc_type["type_key"]
        doc_record = {
            "id": doc_id,
            "applicant_id": None,
            "original_filename": safe_name,
            "stored_filename": stored_name,
            "document_type": type_key,
            "classified_type": type_key,
            "classification_confidence": 0.99,
            "processing_status": "completed",
            "review_status": "verified",
            "file_size": dest_path.stat().st_size,
            "mime_type": mime,
        }
        insert_document(doc_record, db_path=db_path)

        conn = get_db_connection(db_path)
        cur = conn.cursor()
        fields_json = {
            "document_type": type_key,
            "attributes": discovered,
        }
        cur.execute("""
            UPDATE documents 
            SET extracted_text = ?, extracted_fields = ?, extraction_metadata = ?
            WHERE id = ?
        """, (
            text,
            json.dumps(fields_json),
            json.dumps({"status": "success", "filename": safe_name, "spatial_tokens": tokens, "total_pages": ext_res.get("total_pages", 1)}),
            doc_id
        ))
        conn.commit()
        conn.close()

        details = get_document_type_details(doc_type["id"], db_path=db_path)

        return format_resp(True, "Specimen document uploaded and registered successfully.", {
            "sample_document_id": doc_id,
            "sample_filename": safe_name,
            "document_type": doc_type,
            "details": details,
            "has_specimen": True
        })
    except Exception as e:
        logger.error(f"Error uploading sample document for {id_or_key}: {e}")
        return format_resp(False, f"Failed to upload sample document: {str(e)}", status_code=500)

