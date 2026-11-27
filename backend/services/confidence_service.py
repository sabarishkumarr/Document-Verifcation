"""
VeriDoc AI 2.0 — Verification Confidence & Identity Validation Engine

Calculates transparent, documented confidence scores for every verification run:
- Document Extraction Confidence (OCR & attribute extraction quality)
- Attribute Comparison Confidence (Deterministic rule matching)
- Identity Validation Confidence (Declared applicant name vs extracted document identities)
- Overall Verification Confidence with Mandatory Submission Gate (>75% threshold)
"""

import re
import unicodedata
from typing import Dict, Any, List, Optional, Tuple
from rapidfuzz import fuzz

MANDATORY_CONFIDENCE_THRESHOLD = 75.0


def normalize_person_name(name: Optional[str]) -> str:
    """
    Standardize person name by stripping honorifics, punctuation, and multiple spaces.
    """
    if not name or not isinstance(name, str):
        return ""
    # Normalize unicode
    n = unicodedata.normalize("NFKD", name).strip()
    # Lowercase
    n = n.lower()
    # Strip common titles / prefixes
    n = re.sub(r"\b(mr|mrs|ms|dr|shri|smt|kumari|prof)\.?\b", "", n, flags=re.IGNORECASE)
    # Remove punctuation
    n = re.sub(r"[^\w\s]", " ", n)
    # Collapse multiple whitespaces
    n = re.sub(r"\s+", " ", n).strip()
    return n


class VerificationConfidenceEngine:
    """
    Evaluates applicant-level verification confidence based on actual empirical evidence.
    """

    @classmethod
    def validate_applicant_identity(
        cls,
        declared_name: Optional[str],
        documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validates the operator-declared applicant name against extracted names across all uploaded documents.
        Identifies identity mismatches and computes identity validation confidence.
        """
        if not declared_name or not declared_name.strip():
            return {
                "status": "FAIL",
                "score": 0.0,
                "declared_name": declared_name or "",
                "extracted_names": [],
                "message": "IDENTITY VALIDATION FAILED: Applicant Full Name is mandatory.",
                "is_blocking": True
            }

        norm_declared = normalize_person_name(declared_name)
        extracted_names = []

        for d in documents:
            f = d.get("fields") or d.get("extracted_fields") or {}
            if isinstance(f, str):
                import json
                try:
                    f = json.loads(f)
                except Exception:
                    f = {}
            doc_name = f.get("name") or f.get("applicant_name") or f.get("customer_name") or f.get("employee_name")
            if doc_name and str(doc_name).strip():
                extracted_names.append({
                    "doc_id": d.get("id"),
                    "doc_type": d.get("type") or d.get("document_type") or "document",
                    "filename": d.get("filename") or d.get("original_filename") or "document",
                    "raw_name": str(doc_name).strip(),
                    "norm_name": normalize_person_name(str(doc_name))
                })

        if not extracted_names:
            return {
                "status": "REVIEW_REQUIRED",
                "score": 60.0,
                "declared_name": declared_name,
                "extracted_names": [],
                "message": f"Declared applicant name '{declared_name}' recorded. No name attributes detected on uploaded documents to verify against.",
                "is_blocking": False
            }

        # Compare declared name against each extracted document name
        comparison_results = []
        scores = []
        for item in extracted_names:
            norm_doc = item["norm_name"]
            if not norm_doc:
                continue

            # Token sort ratio to handle name ordering (e.g. "Arjun Mehta" vs "Mehta Arjun")
            token_sort_sim = fuzz.token_sort_ratio(norm_declared, norm_doc)
            # Token set ratio to handle middle names and initials (e.g. "Aarav D Kulkarni" vs "Aarav Devansh Kulkarni")
            token_set_sim = fuzz.token_set_ratio(norm_declared, norm_doc)
            sim = max(token_sort_sim, token_set_sim)

            scores.append(sim)
            comparison_results.append({
                "doc_type": item["doc_type"],
                "filename": item["filename"],
                "extracted_name": item["raw_name"],
                "similarity": round(sim, 1),
                "is_match": sim >= 80.0
            })

        min_sim = min(scores) if scores else 0.0
        avg_sim = round(sum(scores) / len(scores), 1) if scores else 0.0

        if min_sim >= 88.0:
            status = "PASS"
            is_blocking = False
            msg = f"Identity Validated: Declared name '{declared_name}' matches extracted document identity ({avg_sim}% match)."
        elif min_sim >= 75.0:
            status = "REVIEW_REQUIRED"
            is_blocking = False
            msg = f"Identity Ambiguity: Declared name '{declared_name}' has minor variation with document names (Average match: {avg_sim}%). Manual review required."
        else:
            status = "IDENTITY_MISMATCH"
            is_blocking = True
            mismatched_doc = next((c for c in comparison_results if c["similarity"] < 75.0), comparison_results[0])
            msg = f"IDENTITY MISMATCH — Declared applicant name '{declared_name}' does not match extracted document identity '{mismatched_doc['extracted_name']}' on {mismatched_doc['doc_type']} ({mismatched_doc['similarity']}% similarity)."

        return {
            "status": status,
            "score": avg_sim,
            "declared_name": declared_name,
            "extracted_names": comparison_results,
            "message": msg,
            "is_blocking": is_blocking
        }

    @classmethod
    def calculate_document_extraction_confidence(
        cls,
        documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Evaluates extraction confidence per document and aggregates across the document set.
        """
        if not documents:
            return {"score": 0.0, "documents": [], "summary": "No documents available for extraction evaluation."}

        doc_confidences = []
        for d in documents:
            f = d.get("fields") or d.get("extracted_fields") or {}
            if isinstance(f, str):
                import json
                try:
                    f = json.loads(f)
                except Exception:
                    f = {}

            # Count extracted non-empty fields
            valid_fields = [k for k, v in f.items() if v and str(v).strip() and str(v).lower() not in ("none", "null", "not detected", "unavailable")]
            field_count = len(valid_fields)

            # Check OCR text availability
            ocr_text = d.get("extracted_text") or ""
            has_ocr = len(ocr_text.strip()) > 30

            # Base extraction score
            if field_count >= 4 and has_ocr:
                doc_score = 96.0
            elif field_count >= 2 and has_ocr:
                doc_score = 88.0
            elif field_count >= 1:
                doc_score = 75.0
            else:
                doc_score = 40.0 if has_ocr else 10.0

            doc_confidences.append({
                "document_id": d.get("id"),
                "document_type": d.get("type") or d.get("document_type") or "document",
                "filename": d.get("filename") or d.get("original_filename") or "document",
                "confidence": doc_score,
                "fields_detected": field_count,
                "ocr_available": has_ocr
            })

        avg_extraction = round(sum(dc["confidence"] for dc in doc_confidences) / len(doc_confidences), 1)
        return {
            "score": avg_extraction,
            "documents": doc_confidences,
            "summary": f"Average extraction quality is {avg_extraction}% across {len(documents)} document(s)."
        }

    @classmethod
    def calculate_overall_confidence(
        cls,
        documents: List[Dict[str, Any]],
        cross_checks: List[Dict[str, Any]],
        discrepancies: List[str],
        declared_name: Optional[str] = None,
        has_expired_doc: bool = False
    ) -> Dict[str, Any]:
        """
        Synthesizes extraction, comparison, and identity validation into an authoritative confidence score.
        Enforces the >75% mandatory submission gate.
        """
        # 1. Identity validation
        identity_val = cls.validate_applicant_identity(declared_name, documents)
        identity_score = identity_val["score"]

        # 2. Document extraction confidence
        extraction_val = cls.calculate_document_extraction_confidence(documents)
        extraction_score = extraction_val["score"]

        # 3. Attribute comparison confidence
        # Evaluated rules
        executed_checks = [c for c in cross_checks if c.get("evaluated")]
        if executed_checks:
            check_scores = [c.get("score", 100.0) for c in executed_checks]
            comparison_score = round(sum(check_scores) / len(check_scores), 1)
        elif len(documents) >= 2:
            comparison_score = 85.0 if not discrepancies else 50.0
        else:
            comparison_score = 65.0  # Single document penalty

        # 4. Weighted Overall Confidence
        # 35% Identity + 45% Comparisons + 20% Extraction Quality
        raw_overall = (0.35 * identity_score) + (0.45 * comparison_score) + (0.20 * extraction_score)
        overall_confidence = round(raw_overall, 1)

        blocking_reasons = []
        corrective_actions = []

        # Penalties for critical failures
        if identity_val.get("is_blocking"):
            overall_confidence = min(overall_confidence, 52.0)
            blocking_reasons.append(identity_val["message"])
            corrective_actions.append("Ensure the declared applicant full name matches the submitted KYC documents exactly.")

        if has_expired_doc:
            overall_confidence = min(overall_confidence, 45.0)
            blocking_reasons.append("One or more submitted documents have expired.")
            corrective_actions.append("Request an updated, currently valid document from the applicant.")

        # Check for critical mismatch in cross-checks
        critical_mismatches = [c for c in cross_checks if c.get("status") == "fail"]
        if critical_mismatches:
            overall_confidence = min(overall_confidence, 58.0)
            for cm in critical_mismatches:
                blocking_reasons.append(cm.get("message", "Critical attribute mismatch between documents."))
            corrective_actions.append("Review conflicting attribute values in the Verification Dossier and request re-submission if fraudulent.")

        if len(documents) < 2:
            overall_confidence = min(overall_confidence, 65.0)
            blocking_reasons.append("Insufficient document evidence: At least 2 supporting KYC documents are required for cross-verification.")
            corrective_actions.append("Upload at least one additional identity or address proof document.")

        # Evaluate against mandatory 75% threshold
        is_submissible = (overall_confidence > MANDATORY_CONFIDENCE_THRESHOLD) and (len(blocking_reasons) == 0)

        if overall_confidence <= MANDATORY_CONFIDENCE_THRESHOLD and not blocking_reasons:
            blocking_reasons.append(
                f"Verification confidence is {overall_confidence}%. The minimum required confidence is greater than {MANDATORY_CONFIDENCE_THRESHOLD}%. Resolve outstanding issues before submitting."
            )
            corrective_actions.append("Ensure higher-resolution document uploads and verify attribute consistency across all submitted files.")

        factors = [
            f"Document extraction quality: {extraction_score}% across {len(documents)} document(s).",
            f"Cross-document comparison consistency: {comparison_score}% across {len(executed_checks)} executed rule(s).",
            f"Identity validation confidence: {identity_score}%."
        ]
        if identity_val["status"] == "PASS":
            factors.append("Declared applicant name matches extracted document identity.")
        if has_expired_doc:
            factors.append("Penalty applied: Document expiration flag detected.")
        if len(documents) < 2:
            factors.append("Penalty applied: Single document submitted (minimum 2 required for triangulation).")

        return {
            "overall_confidence": overall_confidence,
            "required_threshold": MANDATORY_CONFIDENCE_THRESHOLD,
            "is_submissible": is_submissible,
            "document_extraction_confidence": extraction_score,
            "attribute_comparison_confidence": comparison_score,
            "identity_validation": identity_val,
            "factors": factors,
            "blocking_reasons": blocking_reasons,
            "corrective_actions": corrective_actions,
            "documents_evaluated_count": len(documents)
        }
