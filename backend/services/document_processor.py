import json
import logging
import uuid
from pathlib import Path
from typing import Dict, Any, Optional
from werkzeug.datastructures import FileStorage

from backend.utils.helpers import calculate_sha256, sanitize_filename
from backend.database.db import (
    insert_document,
    get_document,
    get_document_type,
    get_documents_by_applicant,
    update_document_extraction,
    update_document_processing_results,
    insert_extracted_attributes_batch,
)
from backend.services.image_preprocessor import ImagePreprocessor
from backend.services.text_extractor import TextExtractor, find_text_bounding_box
from backend.services.classifier import DocumentClassifier
from backend.services.field_extractor import FieldExtractor
from backend.services.validator import DocumentValidator
from backend.services.comparator import CrossDocumentComparator
from backend.services.ai_extractor import AIDocumentExtractor

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Coordinates document intake, storage, OpenCV preprocessing,
    text extraction, document classification, field extraction, validation,
    and cross-document applicant verification.
    """

    def __init__(
        self,
        upload_folder: Path | str,
        processed_folder: Optional[Path | str] = None,
        db_path: Optional[str] = None,
        tesseract_cmd: Optional[str] = None,
        enable_pdf_ocr_fallback: bool = True,
        min_digital_text_chars: int = 15,
        check_images_for_scan: bool = True,
        ocr_dpi: int = 300,
        ai_provider: Optional[str] = None,
        ai_api_key: Optional[str] = None,
        ai_model: Optional[str] = None,
        ai_timeout: int = 30,
        ai_enabled: bool = True
    ):
        self.upload_folder = Path(upload_folder)
        self.upload_folder.mkdir(parents=True, exist_ok=True)
        self.processed_folder = Path(processed_folder) if processed_folder else None
        if self.processed_folder:
            self.processed_folder.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path
        self.preprocessor = ImagePreprocessor(processed_folder=self.processed_folder)
        self.extractor = TextExtractor(
            tesseract_cmd=tesseract_cmd,
            enable_pdf_ocr_fallback=enable_pdf_ocr_fallback,
            min_digital_text_chars=min_digital_text_chars,
            check_images_for_scan=check_images_for_scan,
            ocr_dpi=ocr_dpi,
            preprocessor=self.preprocessor
        )
        self.ai_extractor = AIDocumentExtractor(
            provider=ai_provider,
            api_key=ai_api_key,
            model=ai_model,
            timeout=ai_timeout,
            enabled=ai_enabled,
            db_path=self.db_path
        )

    def save_and_register_document(
        self,
        file_storage: FileStorage,
        applicant_id: Optional[str] = None,
        mime_type: Optional[str] = None,
        document_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Save an uploaded document to storage/uploads/, compute its hash,
        and register it in the SQLite/PostgreSQL database.
        """
        doc_id = str(uuid.uuid4())
        raw_filename = file_storage.filename or "unnamed_document"
        clean_name = sanitize_filename(raw_filename)
        stored_filename = f"{doc_id}_{clean_name}"
        destination_path = self.upload_folder / stored_filename

        file_storage.seek(0)
        file_storage.save(str(destination_path))

        file_size = destination_path.stat().st_size
        file_hash = calculate_sha256(destination_path)

        # Deduplication Guard: Check if identical document content already exists for this applicant
        if applicant_id:
            from backend.database.db import get_db_connection
            conn = get_db_connection(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, stored_filename, processing_status, review_status
                FROM documents
                WHERE applicant_id = ? AND file_hash = ?
            """, (applicant_id, file_hash))
            existing = cursor.fetchone()
            conn.close()

            if existing:
                # Deduplicate: Clean up the redundant destination file on disk
                if destination_path.exists():
                    try:
                        destination_path.unlink()
                    except Exception:
                        pass
                existing_doc = get_document(existing["id"], db_path=self.db_path)
                doc_dict = dict(existing_doc) if existing_doc else dict(existing)
                doc_dict["duplicate_detected"] = True
                return doc_dict

        clean_doc_type = "unknown"
        if document_type and document_type.lower().strip() not in ("auto", "ai_identify", "unknown", ""):
            clean_doc_type = document_type.lower().strip()

        doc_record = {
            "id": doc_id,
            "applicant_id": applicant_id,
            "original_filename": raw_filename,
            "stored_filename": stored_filename,
            "document_type": clean_doc_type,
            "file_size": file_size,
            "file_hash": file_hash,
            "mime_type": mime_type or "application/octet-stream",
            "processing_status": "pending",
            "review_status": "pending"
        }

        insert_document(doc_record, db_path=self.db_path)
        saved_doc = get_document(doc_id, db_path=self.db_path)
        return saved_doc if saved_doc else doc_record

    def extract_document_text(self, document_id: str) -> Dict[str, Any]:
        """
        Extract text from an uploaded document using PyMuPDF (for PDFs)
        or OpenCV + Tesseract OCR (for images and scanned PDF pages).
        """
        doc = get_document(document_id, db_path=self.db_path)
        if not doc:
            return {
                "document_id": document_id,
                "status": "error",
                "error": f"Document with ID '{document_id}' not found in database.",
                "pages": [],
                "full_text": "",
                "character_count": 0
            }

        stored_filename = doc["stored_filename"]
        file_path = self.upload_folder / stored_filename

        if not file_path.exists():
            update_document_extraction(
                document_id=document_id,
                extracted_text="",
                extraction_metadata_json=json.dumps({"error": "File missing on disk"}),
                processing_status="failed",
                db_path=self.db_path
            )
            return {
                "document_id": document_id,
                "filename": doc["original_filename"],
                "status": "error",
                "error": f"Stored file '{stored_filename}' not found on disk.",
                "pages": [],
                "full_text": "",
                "character_count": 0
            }

        result = self.extractor.extract_from_file(
            file_path=file_path,
            original_filename=doc["original_filename"]
        )

        result["document_id"] = document_id
        result["applicant_id"] = doc.get("applicant_id")

        if result["status"] == "success":
            db_status = "completed"
        elif result["status"] == "partial":
            db_status = "partial"
        else:
            db_status = "failed"

        update_document_extraction(
            document_id=document_id,
            extracted_text=result.get("full_text", ""),
            extraction_metadata_json=json.dumps(result),
            processing_status=db_status,
            db_path=self.db_path
        )

        logger.info(
            f"Extraction completed for doc {document_id}: "
            f"status={db_status}, method={result.get('extraction_method')}, "
            f"chars={result.get('character_count', 0)}"
        )

        return result

    def process_document_pipeline(self, document_id: str) -> Dict[str, Any]:
        """
        Hybrid end-to-end processing pipeline:
        1. Digital PDFs: PyMuPDF text extraction.
        2. Scanned PDFs & images: prepared for multimodal understanding.
        3. AI Extraction: multimodal understanding if configured & authorized.
        4. Local Fallback: local DocumentClassifier + FieldExtractor + Tesseract if AI unavailable.
        5. Deterministic Validation: Python ID format, mandatory field, expiry & consistency checks.
        6. Cross-Document Verification: RapidFuzz applicant comparison.
        """
        # Step 1: AI-First Multimodal Classification (No Tesseract/PyMuPDF text extraction or regex classification)
        doc = get_document(document_id, db_path=self.db_path)
        stored_file_path = self.upload_folder / doc["stored_filename"] if doc else None
        raw_text = ""
        extraction = {
            "extraction_method": "ai_multimodal",
            "full_text": "",
            "applicant_id": doc.get("applicant_id") if doc else None,
            "page_count": 1,
        }

        specified_doc_type = doc.get("document_type") if doc and doc.get("document_type") not in ("unknown", "auto", "ai_identify", "") else None
        cls_result = None
        if specified_doc_type:
            cand_type = specified_doc_type
            cls_confidence = 1.0
        elif self.ai_extractor.is_configured() and stored_file_path and stored_file_path.exists():
            cls_result = self.ai_extractor.classify_document(
                file_path=stored_file_path,
                mime_type=doc.get("mime_type") if doc else None,
                original_filename=doc.get("original_filename") if doc else None,
                document_id=document_id,
                applicant_id=doc.get("applicant_id") if doc else None
            )
            cand_type = cls_result.get("document_type", "unknown") if cls_result.get("success") else "unknown"
            cls_confidence = float(cls_result.get("confidence", 0.0)) if cls_result.get("success") else 0.0
        else:
            cand_type = "unknown"
            cls_confidence = 0.0

        # Step 2: Unknown / Unsupported / Unreadable Gate (Stop extraction before schema loading)
        if cand_type == "unknown" or (cls_result and cls_result.get("success") and not cls_result.get("is_readable", True)):
            update_document_processing_results(
                document_id=document_id,
                classified_type="unknown",
                classification_confidence=cls_confidence,
                extracted_fields_json=json.dumps({"classification_metadata": cls_result} if cls_result else {}),
                validation_results_json=json.dumps({"is_valid": False, "flags": ["Document is unknown, unsupported, or unreadable; sent for human review."]}),
                processing_status="completed",
                review_status="manual_review",
                db_path=self.db_path
            )
            return {
                "document_id": document_id,
                "classified_type": "unknown",
                "classification_confidence": cls_confidence,
                "extraction_strategy": "ai_multimodal_classification_only",
                "review_status": "manual_review",
                "message": "Document classified as unknown/unreadable; stopped before schema extraction."
            }

        from backend.services.schema_learner import SchemaLearner
        active_schema = SchemaLearner.get_active_schema(cand_type, db_path=self.db_path)

        # Step 3: Schema-Driven AI Multimodal Extraction
        ai_result = None
        extraction_strategy = "ai_multimodal"
        if self.ai_extractor.is_configured() and stored_file_path and stored_file_path.exists():
            app_id_for_log = doc.get("applicant_id") if doc else None
            ai_result = self.ai_extractor.extract_from_file(
                file_path=stored_file_path,
                mime_type=doc.get("mime_type") if doc else None,
                original_filename=doc.get("original_filename") if doc else None,
                preextracted_text=None,
                document_id=document_id,
                applicant_id=app_id_for_log,
                learned_schema=active_schema
            )

        if ai_result and ai_result.get("success") and ai_result.get("fields"):
            # Multimodal AI extraction succeeded
            extraction_strategy = "ai_multimodal"
            ai_fields = ai_result["fields"]
            ai_doc_type = ai_fields.get("document_type")

            # Validate / correlate with local text classifier if digital text exists
            local_classification = DocumentClassifier.classify(raw_text, db_path=self.db_path) if raw_text else None
            if specified_doc_type:
                classified_type = specified_doc_type
                confidence = 1.0
                dt_info = get_document_type(specified_doc_type, db_path=self.db_path) or {}
                classification = {
                    "classified_type": classified_type,
                    "confidence": confidence,
                    "display_name": dt_info.get("display_name", classified_type.replace("_", " ").title()),
                    "category": dt_info.get("category", "general"),
                    "provider": self.ai_extractor.provider,
                    "scores": local_classification.get("scores") if local_classification else {},
                    "matched_keywords": local_classification.get("matched_keywords") if local_classification else [],
                    "matched_patterns": local_classification.get("matched_patterns") if local_classification else [],
                    "is_user_specified": True
                }
            elif ai_doc_type and ai_doc_type != "unknown":
                classified_type = ai_doc_type
                confidence = ai_fields.get("field_confidence", {}).get("document_type", 0.95)
                classification = {
                    "classified_type": classified_type,
                    "confidence": confidence,
                    "display_name": local_classification.get("display_name") if local_classification else classified_type.replace("_", " ").title(),
                    "category": local_classification.get("category") if local_classification else "general",
                    "provider": self.ai_extractor.provider,
                    "scores": local_classification.get("scores") if local_classification else {},
                    "matched_keywords": local_classification.get("matched_keywords") if local_classification else [],
                    "matched_patterns": local_classification.get("matched_patterns") if local_classification else [],
                    "is_user_specified": False
                }
            elif local_classification and local_classification["classified_type"] != "unknown":
                classified_type = local_classification["classified_type"]
                confidence = local_classification["confidence"]
                classification = {
                    "classified_type": classified_type,
                    "confidence": confidence,
                    "display_name": local_classification.get("display_name", classified_type.replace("_", " ").title()),
                    "category": local_classification.get("category", "general"),
                    "provider": self.ai_extractor.provider,
                    "scores": local_classification.get("scores", {}),
                    "matched_keywords": local_classification.get("matched_keywords", []),
                    "matched_patterns": local_classification.get("matched_patterns", []),
                    "is_user_specified": False
                }
            else:
                classified_type = "unknown"
                confidence = 0.0
                classification = {
                    "classified_type": classified_type,
                    "confidence": confidence,
                    "display_name": "Unknown",
                    "category": "general",
                    "provider": self.ai_extractor.provider,
                    "scores": {},
                    "matched_keywords": [],
                    "matched_patterns": [],
                    "is_user_specified": False
                }
            extracted_fields = ai_fields

        else:
            # Fallback to local rule-based classification and field extraction
            # Local operations (PyMuPDF, Tesseract OCR, OpenCV, regex) do NOT create Gemini usage logs or charges
            extraction_strategy = "local_rule_extraction"
            local_cls = DocumentClassifier.classify(raw_text, db_path=self.db_path)
            if specified_doc_type:
                classified_type = specified_doc_type
                confidence = 1.0
                dt_info = get_document_type(specified_doc_type, db_path=self.db_path) or {}
                classification = {
                    "classified_type": classified_type,
                    "confidence": confidence,
                    "display_name": dt_info.get("display_name", classified_type.replace("_", " ").title()),
                    "category": dt_info.get("category", "general"),
                    "matched_keywords": local_cls.get("matched_keywords", []),
                    "matched_patterns": local_cls.get("matched_patterns", []),
                    "scores": local_cls.get("scores", {}),
                    "is_user_specified": True
                }
            else:
                classification = local_cls
                classified_type = classification["classified_type"]
                confidence = classification["confidence"]
                classification["is_user_specified"] = False
            extracted_fields = FieldExtractor.extract_fields(raw_text, document_type=classified_type, learned_schema=active_schema)

            # Ensure consistent output schema for local fallback
            if "applicant_name" not in extracted_fields:
                extracted_fields["applicant_name"] = extracted_fields.get("name")
            if "date_of_birth" not in extracted_fields:
                extracted_fields["date_of_birth"] = extracted_fields.get("dob")
            if "identification_number" not in extracted_fields:
                extracted_fields["identification_number"] = extracted_fields.get("id_number")
            if "document_type" not in extracted_fields:
                extracted_fields["document_type"] = classified_type
            if "extraction_method" not in extracted_fields:
                extracted_fields["extraction_method"] = extraction.get("extraction_method", "digital_text")
            if "field_confidence" not in extracted_fields:
                extracted_fields["field_confidence"] = {
                    "document_type": confidence,
                    "applicant_name": 0.85 if extracted_fields.get("name") else 0.0,
                    "identification_number": 0.90 if extracted_fields.get("id_number") else 0.0,
                    "date_of_birth": 0.85 if extracted_fields.get("dob") else 0.0,
                }
            if "source_evidence" not in extracted_fields:
                extracted_fields["source_evidence"] = {
                    "page_number": 1,
                    "text_snippet": raw_text[:120].strip() if raw_text else None,
                    "notes": "Extracted via local PyMuPDF / Tesseract rule pipeline."
                }
            if "manual_review_required" not in extracted_fields:
                is_kyc = classified_type in ("pan", "aadhaar", "passport", "voter_id", "driving_licence")
                if is_kyc:
                    extracted_fields["manual_review_required"] = (
                        not extracted_fields.get("name") or not extracted_fields.get("id_number")
                    )
                else:
                    extracted_fields["manual_review_required"] = False

        # Ensure normalized attributes list is populated for both AI and local pipelines
        if not extracted_fields.get("attributes"):
            local_attributes = []
            seen_keys = set()
            for f_key, f_lbl, f_dtype in [
                ("name", "Applicant Name", "string"),
                ("applicant_name", "Applicant Name", "string"),
                ("id_number", "Identification Number", "string"),
                ("identification_number", "Identification Number", "string"),
                ("dob", "Date of Birth", "date"),
                ("date_of_birth", "Date of Birth", "date"),
                ("gender", "Gender", "string"),
                ("father_name", "Father's Name", "string"),
                ("expiry_date", "Expiry Date", "date"),
            ]:
                val = extracted_fields.get(f_key)
                if val and f_key not in seen_keys:
                    local_attributes.append({
                        "attribute_key": f_key,
                        "display_label": f_lbl,
                        "attribute_value": str(val),
                        "data_type": f_dtype,
                        "confidence_score": 0.88,
                        "bounding_box": None,
                        "page_number": 1,
                        "provenance": extraction_strategy,
                        "is_custom": False
                    })
                    seen_keys.add(f_key)

            extra = extracted_fields.get("extra_fields", {})
            if isinstance(extra, dict):
                for e_key, e_val in extra.items():
                    if e_val and e_key not in seen_keys and isinstance(e_val, (str, int, float)):
                        dtype = "currency" if any(cur in e_key for cur in ["salary", "amount", "balance", "total", "pay"]) else "string"
                        local_attributes.append({
                            "attribute_key": e_key,
                            "display_label": e_key.replace("_", " ").title(),
                            "attribute_value": str(e_val),
                            "data_type": dtype,
                            "confidence_score": 0.85,
                            "bounding_box": None,
                            "page_number": 1,
                            "provenance": extraction_strategy,
                            "is_custom": False
                        })
                        seen_keys.add(e_key)

            extracted_fields["attributes"] = local_attributes

        # Resolve spatial bounding boxes for extracted attributes against spatial_tokens
        spatial_tokens = extraction.get("spatial_tokens", [])
        attributes_list = extracted_fields.get("attributes", [])
        if attributes_list and spatial_tokens:
            for attr in attributes_list:
                if not attr.get("bounding_box"):
                    val_to_find = attr.get("attribute_value")
                    p_num = attr.get("page_number", 1)
                    found_bbox = find_text_bounding_box(val_to_find, spatial_tokens, page_number=p_num)
                    if found_bbox and len(found_bbox) == 4:
                        attr["bounding_box"] = {
                            "ymin": found_bbox[0],
                            "xmin": found_bbox[1],
                            "ymax": found_bbox[2],
                            "xmax": found_bbox[3]
                        }

        # Persist normalized attributes into document_extracted_attributes table
        if attributes_list:
            try:
                insert_extracted_attributes_batch(document_id, attributes_list, db_path=self.db_path)
            except Exception as batch_exc:
                logger.warning(f"Could not persist extracted attributes to DB: {batch_exc}")

        # Step 3: Rule Validation & Expiry Checking (ALWAYS executed deterministically in Python)
        validation = DocumentValidator.validate(classified_type, extracted_fields, raw_text=raw_text)

        # Step 4: Save results into SQLite
        proc_status = "completed" if extraction.get("status") in ("success", "partial") or (ai_result and ai_result.get("success")) else "failed"
        update_document_processing_results(
            document_id=document_id,
            classified_type=classified_type,
            classification_confidence=confidence,
            extracted_fields=extracted_fields,
            validation_results=validation,
            processing_status=proc_status,
            db_path=self.db_path
        )

        # Step 5: Cross-Document Applicant Comparison (Strict Applicant Isolation)
        applicant_id = extraction.get("applicant_id") or (doc.get("applicant_id") if doc else None)
        cross_comparison = None
        if applicant_id:
            from backend.database.db import get_applicant
            from backend.database.db import consolidate_applicant_name, recompute_applicant_status
            appl_name = consolidate_applicant_name(applicant_id, db_path=self.db_path)
            applicant_obj = get_applicant(applicant_id, db_path=self.db_path)
            if not appl_name and applicant_obj:
                appl_name = applicant_obj.get("name")

            all_applicant_docs = get_documents_by_applicant(applicant_id, db_path=self.db_path, distinct_types=True)
            # Hydrate extracted fields and validation results if stored as JSON
            hydrated_docs = []
            for d in all_applicant_docs:
                f_dict = {}
                if d.get("extracted_fields"):
                    try:
                        f_dict = json.loads(d["extracted_fields"]) if isinstance(d["extracted_fields"], str) else d["extracted_fields"]
                    except Exception:
                        f_dict = {}
                v_dict = {}
                if d.get("validation_results"):
                    try:
                        v_dict = json.loads(d["validation_results"]) if isinstance(d["validation_results"], str) else d["validation_results"]
                    except Exception:
                        v_dict = {}
                hydrated_docs.append({
                    "id": d["id"],
                    "applicant_id": applicant_id,
                    "original_filename": d["original_filename"],
                    "classified_type": d.get("classified_type") or d.get("document_type"),
                    "extracted_fields": f_dict,
                    "validation_results": v_dict,
                    "review_status": d.get("review_status")
                })
            cross_comparison = CrossDocumentComparator.compare_applicant_documents(
                hydrated_docs,
                applicant_name=appl_name,
                applicant_id=applicant_id
            )
            from backend.database.db import recompute_applicant_status
            recompute_applicant_status(applicant_id, db_path=self.db_path)

        # Check if type is unknown or unregistered
        is_unregistered = classified_type == "unknown" or get_document_type(classified_type, db_path=self.db_path) is None
        classification["is_unregistered_type"] = is_unregistered
        classification["suggest_register_type"] = is_unregistered

        return {
            "document_id": document_id,
            "applicant_id": applicant_id,
            "filename": extraction.get("filename"),
            "extraction_strategy": extraction_strategy,
            "ai_status": self.ai_extractor.get_status(),
            "extraction": extraction,
            "classification": classification,
            "extracted_fields": extracted_fields,
            "validation": validation,
            "cross_comparison": cross_comparison,
            "processing_status": proc_status
        }

    def preprocess_image(self, document_id: str) -> Dict[str, Any]:
        """
        Preprocess an image document with OpenCV and save the result to storage/processed/.
        """
        doc = get_document(document_id, db_path=self.db_path)
        if not doc:
            raise ValueError(f"Document '{document_id}' not found.")

        stored_path = self.upload_folder / doc["stored_filename"]
        img = self.preprocessor.read_image_from_path(stored_path)
        if img is None:
            raise ValueError(f"Failed to read image at '{stored_path}'.")

        processed, meta = self.preprocessor.preprocess_image(img)
        saved_name = f"proc_{doc['stored_filename']}.png"
        saved_path = self.preprocessor.save_processed_image(processed, saved_name)

        return {
            "document_id": document_id,
            "processed_path": str(saved_path) if saved_path else None,
            "metadata": meta
        }
