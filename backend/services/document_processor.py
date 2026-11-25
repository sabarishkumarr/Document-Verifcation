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
    get_documents_by_applicant,
    update_document_extraction,
    update_document_processing_results,
)
from backend.services.image_preprocessor import ImagePreprocessor
from backend.services.text_extractor import TextExtractor
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
            enabled=ai_enabled
        )

    def save_and_register_document(
        self,
        file_storage: FileStorage,
        applicant_id: Optional[str] = None,
        mime_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Save an uploaded document to storage/uploads/, compute its hash,
        and register it in the SQLite database.
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

        doc_record = {
            "id": doc_id,
            "applicant_id": applicant_id,
            "original_filename": raw_filename,
            "stored_filename": stored_filename,
            "document_type": "unknown",
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
        # Step 1: Text Extraction (Digital PDF or Local OCR fallback)
        extraction = self.extract_document_text(document_id)
        raw_text = extraction.get("full_text", "")

        doc = get_document(document_id, db_path=self.db_path)
        stored_file_path = self.upload_folder / doc["stored_filename"] if doc else None

        # Step 2: Hybrid AI Multimodal Extraction Attempt
        ai_result = None
        extraction_strategy = "local_rule_extraction"

        if self.ai_extractor.is_configured() and stored_file_path and stored_file_path.exists():
            ai_result = self.ai_extractor.extract_from_file(
                file_path=stored_file_path,
                mime_type=doc.get("mime_type") if doc else None,
                original_filename=doc.get("original_filename") if doc else None,
                preextracted_text=raw_text
            )

        if ai_result and ai_result.get("success") and ai_result.get("fields"):
            # Multimodal AI extraction succeeded
            extraction_strategy = "ai_multimodal"
            ai_fields = ai_result["fields"]
            ai_doc_type = ai_fields.get("document_type")

            # Validate / correlate with local text classifier if digital text exists
            local_classification = DocumentClassifier.classify(raw_text) if raw_text else None
            if ai_doc_type and ai_doc_type != "unknown":
                classified_type = ai_doc_type
                confidence = ai_fields.get("field_confidence", {}).get("document_type", 0.95)
            elif local_classification and local_classification["classified_type"] != "unknown":
                classified_type = local_classification["classified_type"]
                confidence = local_classification["confidence"]
            else:
                classified_type = "unknown"
                confidence = 0.0

            classification = {
                "classified_type": classified_type,
                "confidence": confidence,
                "provider": self.ai_extractor.provider,
                "scores": local_classification.get("scores") if local_classification else {},
                "matched_keywords": local_classification.get("matched_keywords") if local_classification else [],
                "matched_patterns": local_classification.get("matched_patterns") if local_classification else []
            }
            extracted_fields = ai_fields

        else:
            # Fallback to local rule-based classification and field extraction
            extraction_strategy = "local_rule_extraction"
            classification = DocumentClassifier.classify(raw_text)
            classified_type = classification["classified_type"]
            confidence = classification["confidence"]
            extracted_fields = FieldExtractor.extract_fields(raw_text, document_type=classified_type)

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
                extracted_fields["manual_review_required"] = (
                    not extracted_fields.get("name") or not extracted_fields.get("id_number")
                )

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
