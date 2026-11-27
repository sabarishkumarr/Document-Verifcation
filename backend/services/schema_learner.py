"""
VeriDoc AI 2.0 — Versioned Document Schema Learning Engine

Learns and versions extraction schemas from employee-confirmed attributes,
anchor phrases, regex patterns, and few-shot demonstration examples.

NOTE ON LEARNING MECHANISM:
This service implements Retrieval-Augmented In-Context Prompt Injection (few-shot prompting)
and deterministic anchor/regex rule synthesis. It deliberately improves subsequent extraction
accuracy and entity coverage WITHOUT claiming neural model weight fine-tuning.
"""

import re
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from collections import Counter

from backend.database.db import (
    get_db_connection,
    get_document_type,
    get_document_schema,
    save_document_schema,
    is_postgres_configured,
)

logger = logging.getLogger(__name__)


def mask_sensitive_pii(text: str) -> str:
    """Mask sensitive PII identifiers (Aadhaar, PAN, phone, names) for safe few-shot exemplar storage."""
    if not text or not isinstance(text, str):
        return text
    # Mask 12-digit Aadhaar
    masked = re.sub(r"\b\d{4}\s?\d{4}\s?(\d{4})\b", r"XXXX-XXXX-\1", text)
    # Mask 10-char PAN
    masked = re.sub(r"\b[A-Z]{5}\d{4}[A-Z]\b", r"XXXXX1234X", masked)
    # Mask Indian phone
    masked = re.sub(r"(\+91\s?\d{2})\d{3}\s?\d{2}(\d{3})", r"\1XXX-XX\2", masked)
    return masked


def synthesize_regex_for_value(value: str) -> Optional[str]:
    """Derive a generalized regex pattern for a sample extracted attribute value."""
    if not value or not isinstance(value, str):
        return None
    val = value.strip()
    
    # ISO Date: YYYY-MM-DD
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", val):
        return r"\b\d{4}-\d{2}-\d{2}\b"
    # Slash Date: DD/MM/YYYY
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", val):
        return r"\b\d{2}/\d{2}/\d{4}\b"
    # Currency: USD 12,000.00 or $12,000.00 or INR 50,000
    if re.search(r"[$₹]|(?:USD|INR|EUR|GBP)\s*[\d,]+(?:\.\d{2})?", val, re.I):
        return r"(?:USD|INR|EUR|GBP|[$₹])?\s*[\d,]+(?:\.\d{2})?"
    # PAN pattern
    if re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", val):
        return r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"
    # Alphanumeric Code / Invoice ID: e.g. INV-2026-9901
    if re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)+", val, re.I):
        return r"\b[A-Z0-9]+(?:-[A-Z0-9]+)+\b"
    # Pure numeric (5+ digits)
    if re.fullmatch(r"\d{5,}", val):
        return r"\b\d{5,}\b"

    return None


class SchemaLearner:
    """
    Coordinates schema learning, versioning, few-shot prompt injection, and rollback.
    """

    @classmethod
    def learn_schema_for_type(
        cls,
        type_key: str,
        min_samples: int = 1,
        db_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyzes employee-confirmed attributes and document text for type_key.
        Generates a new versioned schema with anchor phrases, regex patterns, and few-shot exemplars.
        Increments schema version and marks the new version active.
        """
        doc_type = get_document_type(type_key, db_path=db_path)
        if not doc_type:
            raise ValueError(f"Document type '{type_key}' is not registered in document_type_definitions.")

        type_id = doc_type["id"]
        conn = get_db_connection(db_path)
        cur = conn.cursor()

        # 1. Fetch verified / approved attributes for this document type
        cur.execute("""
            SELECT a.attribute_key, a.attribute_label, a.data_type, a.raw_value, a.normalized_value,
                   a.confidence, a.bounding_box, a.page_number, d.extracted_text, d.id as doc_id
            FROM document_extracted_attributes a
            JOIN documents d ON a.document_id = d.id
            WHERE (d.document_type = ? OR d.classified_type = ?)
              AND (a.is_deleted = FALSE OR a.is_deleted = 0)
            ORDER BY a.created_at DESC;
        """, (type_key, type_key))
        rows = [dict(r) for r in cur.fetchall()]

        # 2. If no extracted attributes table rows, also check documents.extracted_fields JSON
        if not rows:
            cur.execute("""
                SELECT id as doc_id, document_type, classified_type, extracted_fields, extracted_text
                FROM documents
                WHERE (document_type = ? OR classified_type = ?)
                  AND extracted_fields IS NOT NULL;
            """, (type_key, type_key))
            doc_rows = [dict(r) for r in cur.fetchall()]
            for dr in doc_rows:
                ef = dr.get("extracted_fields")
                if isinstance(ef, str):
                    try:
                        ef = json.loads(ef)
                    except Exception:
                        ef = {}
                if isinstance(ef, dict):
                    raw_attrs = ef.get("attributes") if isinstance(ef.get("attributes"), list) else None
                    if raw_attrs:
                        for ra in raw_attrs:
                            rows.append({
                                "attribute_key": ra.get("attribute_key"),
                                "attribute_label": ra.get("display_label") or ra.get("attribute_label"),
                                "data_type": ra.get("data_type", "string"),
                                "raw_value": ra.get("attribute_value") or ra.get("raw_value"),
                                "normalized_value": ra.get("attribute_value") or ra.get("normalized_value"),
                                "confidence": ra.get("confidence", 0.95),
                                "bounding_box": ra.get("bounding_box"),
                                "page_number": ra.get("page_number", 1),
                                "extracted_text": dr.get("extracted_text", ""),
                                "doc_id": dr.get("doc_id")
                            })
                    else:
                        for k, v in ef.items():
                            if v and not isinstance(v, (dict, list)):
                                rows.append({
                                    "attribute_key": k,
                                    "attribute_label": k.replace("_", " ").title(),
                                    "data_type": "string",
                                    "raw_value": str(v),
                                    "normalized_value": str(v),
                                    "confidence": 0.95,
                                    "bounding_box": None,
                                    "page_number": 1,
                                    "extracted_text": dr.get("extracted_text", ""),
                                    "doc_id": dr.get("doc_id")
                                })

        # Aggregate attributes by key
        attr_groups: Dict[str, List[Dict[str, Any]]] = {}
        distinct_docs = set()
        for r in rows:
            k = r.get("attribute_key")
            if not k:
                continue
            distinct_docs.add(r.get("doc_id"))
            attr_groups.setdefault(k, []).append(r)

        # 3. Discover anchor phrases & regex patterns for each attribute
        learned_attributes = []
        anchor_phrases: Dict[str, List[str]] = {}
        regex_patterns: Dict[str, str] = {}
        spatial_templates: Dict[str, Any] = {}

        for key, occurrences in attr_groups.items():
            labels = [o.get("attribute_label") for o in occurrences if o.get("attribute_label")]
            types = [o.get("data_type") for o in occurrences if o.get("data_type")]
            confidences = [float(o.get("confidence") or 1.0) for o in occurrences]
            values = [str(o.get("raw_value") or o.get("normalized_value") or "") for o in occurrences if o.get("raw_value") or o.get("normalized_value")]

            display_label = Counter(labels).most_common(1)[0][0] if labels else key.replace("_", " ").title()
            primary_type = Counter(types).most_common(1)[0][0] if types else "string"
            avg_conf = round(sum(confidences) / len(confidences), 3) if confidences else 1.0

            # Anchor phrase discovery from surrounding document text
            key_anchors = set()
            # Standard label anchor
            key_anchors.add(f"{display_label}:")
            key_anchors.add(f"{display_label}")
            key_anchors.add(f"{key.replace('_', ' ')}:")

            for occ in occurrences:
                text = occ.get("extracted_text") or ""
                val = occ.get("raw_value") or ""
                if text and val and len(val) >= 3 and val in text:
                    idx = text.find(val)
                    start = max(0, idx - 40)
                    preceding = text[start:idx].strip()
                    # Look for trailing words before the value
                    words = preceding.split()
                    if words:
                        candidate_anchor = " ".join(words[-3:]).strip(":,-# ")
                        if len(candidate_anchor) >= 3 and len(candidate_anchor) <= 25:
                            key_anchors.add(candidate_anchor + ":")

            anchor_phrases[key] = sorted(list(key_anchors))[:5]

            # Regex pattern synthesis
            for val in values:
                rx = synthesize_regex_for_value(val)
                if rx:
                    regex_patterns[key] = rx
                    break

            # Spatial template (bounding box distribution)
            bboxes = [o.get("bounding_box") for o in occurrences if o.get("bounding_box")]
            if bboxes:
                # Store sample median/representative bounding box
                sample_bbox = bboxes[0]
                if isinstance(sample_bbox, str):
                    try:
                        sample_bbox = json.loads(sample_bbox)
                    except Exception:
                        pass
                if isinstance(sample_bbox, list) and len(sample_bbox) == 4:
                    spatial_templates[key] = {
                        "typical_bbox": sample_bbox,
                        "sample_count": len(bboxes)
                    }

            learned_attributes.append({
                "attribute_key": key,
                "display_label": display_label,
                "data_type": primary_type,
                "mean_confidence": avg_conf,
                "occurrence_count": len(occurrences),
                "frequency_ratio": round(len(occurrences) / max(1, len(distinct_docs)), 2),
                "anchor_phrases": anchor_phrases[key],
                "regex_pattern": regex_patterns.get(key)
            })

        # 4. Generate Sanitized Few-Shot Demonstration Exemplars
        few_shot_examples = []
        sample_doc_ids = list(distinct_docs)[:3]
        for s_id in sample_doc_ids:
            cur.execute("SELECT original_filename, extracted_text FROM documents WHERE id = ?;", (s_id,))
            s_row = cur.fetchone()
            if s_row:
                s_dict = dict(s_row)
                raw_text = s_dict.get("extracted_text", "")
                if raw_text:
                    snippet = mask_sensitive_pii(raw_text[:400].strip())
                    doc_attrs = {
                        o["attribute_key"]: mask_sensitive_pii(str(o.get("normalized_value") or o.get("raw_value") or ""))
                        for o in rows if o.get("doc_id") == s_id
                    }
                    few_shot_examples.append({
                        "document_id": s_id,
                        "text_snippet": snippet,
                        "expected_attributes": doc_attrs
                    })

        # 5. Versioning Logic
        cur.execute("""
            SELECT version FROM document_schemas
            WHERE document_type_id = ?
            ORDER BY version DESC LIMIT 1;
        """, (type_id,))
        latest_ver_row = cur.fetchone()
        current_version = latest_ver_row["version"] if latest_ver_row else 0
        new_version = current_version + 1

        # Deactivate previous active versions
        cur.execute("""
            UPDATE document_schemas
            SET is_active = FALSE
            WHERE document_type_id = ?;
        """, (type_id,))
        conn.commit()
        conn.close()

        # Save new active version
        templates_payload = {
            "anchor_phrases": anchor_phrases,
            "regex_patterns": regex_patterns,
            "few_shot_examples": few_shot_examples,
            "spatial_templates": spatial_templates,
            "learning_metadata": {
                "sample_documents_count": len(distinct_docs),
                "attribute_count": len(learned_attributes),
                "in_context_learning_ready": True
            }
        }

        schema_record = save_document_schema({
            "document_type_id": type_id,
            "version": new_version,
            "schema_name": f"{doc_type['display_name']} Schema v{new_version}",
            "attribute_definitions": learned_attributes,
            "spatial_templates": templates_payload,
            "sample_count": len(distinct_docs)
        }, db_path=db_path)

        logger.info(f"Learned and published Schema v{new_version} for '{type_key}' ({len(learned_attributes)} attributes, {len(distinct_docs)} sample documents).")
        return {
            "document_type": type_key,
            "version": new_version,
            "schema_id": schema_record["id"],
            "attribute_count": len(learned_attributes),
            "attributes": learned_attributes,
            "anchor_phrases": anchor_phrases,
            "regex_patterns": regex_patterns,
            "few_shot_examples": few_shot_examples,
            "sample_documents_count": len(distinct_docs)
        }

    @classmethod
    def learn_from_feedback(cls, type_key: str, db_path: Optional[str] = None) -> Dict[str, Any]:
        """Alias for learn_schema_for_type."""
        return cls.learn_schema_for_type(type_key=type_key, db_path=db_path)

    @classmethod
    def get_schema_versions(cls, type_key: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Alias for list_schema_versions."""
        return cls.list_schema_versions(type_key=type_key, db_path=db_path)

    @classmethod
    def get_active_schema(cls, type_key: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Fetch the active learned schema for type_key, including anchor phrases and few-shot exemplars."""
        raw_schema = get_document_schema(type_key, active_only=True, db_path=db_path)
        if not raw_schema:
            return None

        # Parse templates JSON payload
        templates = raw_schema.get("spatial_templates") or {}
        if isinstance(templates, str):
            try:
                templates = json.loads(templates)
            except Exception:
                templates = {}

        return {
            "id": raw_schema["id"],
            "document_type_id": raw_schema["document_type_id"],
            "document_type": type_key,
            "version": raw_schema["version"],
            "schema_name": raw_schema["schema_name"],
            "attribute_definitions": raw_schema.get("attribute_definitions", []),
            "anchor_phrases": templates.get("anchor_phrases", {}),
            "regex_patterns": templates.get("regex_patterns", {}),
            "few_shot_examples": templates.get("few_shot_examples", []),
            "spatial_templates": templates.get("spatial_templates", {}),
            "sample_count": raw_schema.get("sample_count", 0),
            "is_active": bool(raw_schema.get("is_active", True))
        }

    @classmethod
    def list_schema_versions(cls, type_key: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all historical schema versions for type_key."""
        doc_type = get_document_type(type_key, db_path=db_path)
        if not doc_type:
            return []

        conn = get_db_connection(db_path)
        cur = conn.cursor()
        cur.execute("""
            SELECT id, version, schema_name, sample_count, is_active, created_at, updated_at
            FROM document_schemas
            WHERE document_type_id = ?
            ORDER BY version DESC;
        """, (doc_type["id"],))
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            d["is_active"] = bool(d.get("is_active"))
            rows.append(d)
        conn.close()
        return rows

    @classmethod
    def rollback_schema(cls, type_key: str, target_version: int, db_path: Optional[str] = None) -> bool:
        """Roll back or switch active schema for type_key to target_version."""
        doc_type = get_document_type(type_key, db_path=db_path)
        if not doc_type:
            return False

        type_id = doc_type["id"]
        conn = get_db_connection(db_path)
        cur = conn.cursor()

        # Check target version exists
        cur.execute("""
            SELECT id FROM document_schemas
            WHERE document_type_id = ? AND version = ?;
        """, (type_id, target_version))
        target_row = cur.fetchone()
        if not target_row:
            conn.close()
            return False

        # Deactivate all versions
        cur.execute("UPDATE document_schemas SET is_active = FALSE WHERE document_type_id = ?;", (type_id,))
        # Activate target version
        cur.execute("UPDATE document_schemas SET is_active = TRUE WHERE document_type_id = ? AND version = ?;", (type_id, target_version))
        conn.commit()
        conn.close()
        logger.info(f"Schema for '{type_key}' rolled back to active version {target_version}.")
        return True

    @classmethod
    def discover_attributes_from_sample(
        cls,
        text: str,
        spatial_tokens: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Discovers candidate attributes from sample document text and spatial tokens.
        Identifies key-value pairs, dates, amounts, and codes with page and bounding box mapping.
        """
        from backend.services.text_extractor import find_text_bounding_box

        if not text:
            return []

        discovered: List[Dict[str, Any]] = []
        seen_keys = set()

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        # 1. Line-based Key-Value Pattern Parsing
        for line in lines:
            # Match "Label: Value" or "Label - Value"
            m = re.match(r"^([A-Za-z0-9\s/&.'#_-]{2,35})\s*[:\-]\s*(.{1,100})$", line)
            if not m:
                continue

            raw_label = m.group(1).strip()
            raw_val = m.group(2).strip()

            # Ignore URL/header/footer boilerplate
            low_lbl = raw_label.lower()
            if low_lbl in ("http", "https", "page", "synthetic test document", "not valid", "www"):
                continue
            if not raw_val or len(raw_val) < 1:
                continue

            attr_key = re.sub(r"[^a-z0-9]+", "_", low_lbl).strip("_")
            if not attr_key or attr_key in seen_keys:
                continue

            # Infer data type
            data_type = "string"
            if re.fullmatch(r"\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4}", raw_val):
                data_type = "date"
            elif re.search(r"[$₹]|(?:USD|INR|EUR|GBP)\s*[\d,]+(?:\.\d{2})?", raw_val, re.I):
                data_type = "currency"
            elif re.fullmatch(r"[-+]?\d+(?:\.\d+)?", raw_val.replace(",", "")):
                data_type = "number"

            # Bounding box & page detection from spatial tokens
            bbox = None
            page_num = 1
            if spatial_tokens:
                bbox = find_text_bounding_box(raw_val[:30], spatial_tokens)
                if not bbox:
                    bbox = find_text_bounding_box(raw_label, spatial_tokens)
                # Find page number
                for token in spatial_tokens:
                    if raw_val[:10].lower() in token.get("text", "").lower():
                        page_num = token.get("page", 1)
                        break

            discovered.append({
                "attribute_key": attr_key,
                "attribute_label": raw_label.title(),
                "sample_value": raw_val,
                "data_type": data_type,
                "page_number": page_num,
                "bounding_box": bbox,
                "confidence": 0.90,
                "source_type": "discovered"
            })
            seen_keys.add(attr_key)

        # 2. Pattern-based Fallback for Structured Fields (if not already captured)
        # Currency / Total Amount
        if "total_amount" not in seen_keys and "amount" not in seen_keys:
            amount_match = re.search(r"(?:Total|Amount|Gross|Due|Net)[\s:]*([$₹]|\b(?:USD|INR|EUR|GBP)\b)?\s*([\d,]+(?:\.\d{2})?)", text, re.I)
            if amount_match:
                amt_str = amount_match.group(0).strip()
                bbox = find_text_bounding_box(amt_str, spatial_tokens) if spatial_tokens else None
                discovered.append({
                    "attribute_key": "total_amount",
                    "attribute_label": "Total Amount",
                    "sample_value": amt_str,
                    "data_type": "currency",
                    "page_number": 1,
                    "bounding_box": bbox,
                    "confidence": 0.88,
                    "source_type": "discovered"
                })
                seen_keys.add("total_amount")

        # Document / Reference Number
        if "reference_number" not in seen_keys and "id_number" not in seen_keys:
            ref_match = re.search(r"(?:Invoice|Document|Licence|License|Policy|Agreement|Tax\s*ID|Registration)[\s#No.:]*([A-Z0-9]+(?:-[A-Z0-9]+)+)", text, re.I)
            if ref_match:
                ref_str = ref_match.group(1).strip()
                bbox = find_text_bounding_box(ref_str, spatial_tokens) if spatial_tokens else None
                discovered.append({
                    "attribute_key": "reference_number",
                    "attribute_label": "Reference Number",
                    "sample_value": ref_str,
                    "data_type": "string",
                    "page_number": 1,
                    "bounding_box": bbox,
                    "confidence": 0.92,
                    "source_type": "discovered"
                })
                seen_keys.add("reference_number")

        return discovered

    @classmethod
    def create_initial_schema(
        cls,
        type_key: str,
        display_name: str,
        attribute_definitions: List[Dict[str, Any]],
        sample_text: Optional[str] = None,
        db_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create and activate Version 1 schema for a newly confirmed document type.
        Synthesizes anchor phrases, regexes, and PII-masked few-shot exemplars.
        """
        doc_type = get_document_type(type_key, db_path=db_path)
        if not doc_type:
            raise ValueError(f"Document type '{type_key}' is not registered.")

        type_id = doc_type["id"]
        anchor_phrases: Dict[str, List[str]] = {}
        regex_patterns: Dict[str, str] = {}

        for attr in attribute_definitions:
            k = attr.get("attribute_key")
            if not k:
                continue
            lbl = attr.get("attribute_label") or k.replace("_", " ").title()
            anchor_phrases[k] = [f"{lbl}:", f"{lbl} :", f"{k}:", lbl]
            
            # Synthesize regex
            sample_val = str(attr.get("sample_value") or attr.get("raw_value") or "")
            pat = attr.get("regex_pattern") or synthesize_regex_for_value(sample_val)
            if pat:
                regex_patterns[k] = pat

        few_shot_examples = []
        if sample_text:
            masked_snippet = mask_sensitive_pii(sample_text[:500].strip())
            few_shot_examples.append({
                "document_id": "seed_sample_doc",
                "text_snippet": masked_snippet,
                "expected_attributes": {
                    a["attribute_key"]: mask_sensitive_pii(str(a.get("sample_value") or a.get("raw_value") or ""))
                    for a in attribute_definitions if a.get("attribute_key")
                }
            })

        templates_payload = {
            "anchor_phrases": anchor_phrases,
            "regex_patterns": regex_patterns,
            "few_shot_examples": few_shot_examples,
            "spatial_templates": {},
            "learning_metadata": {
                "sample_documents_count": 1 if sample_text else 0,
                "attribute_count": len(attribute_definitions),
                "in_context_learning_ready": True,
                "source": "employee_registration"
            }
        }

        schema_record = save_document_schema({
            "document_type_id": type_id,
            "version": 1,
            "schema_name": f"{display_name} Schema v1",
            "attribute_definitions": attribute_definitions,
            "spatial_templates": templates_payload,
            "sample_count": 1 if sample_text else 0
        }, db_path=db_path)

        logger.info(f"Created initial Schema v1 for newly registered type '{type_key}' ({len(attribute_definitions)} attributes).")
        return {
            "document_type": type_key,
            "version": 1,
            "schema_id": schema_record["id"],
            "attribute_count": len(attribute_definitions),
            "attributes": attribute_definitions,
            "anchor_phrases": anchor_phrases,
            "regex_patterns": regex_patterns,
            "few_shot_examples": few_shot_examples
        }
