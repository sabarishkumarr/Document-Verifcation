"""
VeriDoc AI 2.0 — Milestone 4: Versioned Schema Learning & Evaluation Benchmark Test Suite

Validates:
1. Versioned schema learning from employee-confirmed attributes, anchor phrases, regexes, and few-shot exemplars.
2. Version progression and atomic rollback.
3. In-context extraction improvement using learned anchors and regexes (without claiming fine-tuning).
4. Rigorous evaluation benchmark over the authorized 10-person synthetic KYC dataset:
   - Classification accuracy
   - Precision, Recall, and F1-score
   - Character Error Rate (CER) via normalized edit distance
   - PII privacy preservation and masking
5. REST API endpoints for schemas and evaluation benchmarks.
"""

import io
import json
import pytest
from pathlib import Path

from backend.app import create_app
from backend.database.db import (
    init_db,
    insert_document,
    insert_extracted_attribute,
    create_api_key,
    get_document_type,
)
from backend.services.schema_learner import SchemaLearner, mask_sensitive_pii, synthesize_regex_for_value
from backend.services.field_extractor import FieldExtractor
from backend.services.evaluator import DatasetEvaluator, compute_cer, levenshtein_distance


@pytest.fixture
def app(tmp_path):
    test_db = str(tmp_path / "test_m4.db")
    app = create_app("testing")
    app.config["DATABASE_PATH"] = test_db
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    app.config["PROCESSED_FOLDER"] = str(tmp_path / "processed")
    app.config["TESTING"] = True
    app.config["AI_PROVIDER"] = "mock"

    with app.app_context():
        init_db(test_db)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_key(app):
    with app.app_context():
        db_path = app.config["DATABASE_PATH"]
        raw_key, record = create_api_key(
            name="Admin Benchmark Key",
            permissions=["documents:read", "documents:write", "admin"],
            db_path=db_path
        )
        return raw_key


class TestSchemaLearningAndVersioning:
    """Tests schema learning synthesis, version progression, and rollback."""

    def test_pii_masking_helper(self):
        text = "Aadhaar: 5432 9876 1234, PAN: ABCPM1234D, Phone: +91 98200 11001"
        masked = mask_sensitive_pii(text)
        assert "5432 9876 1234" not in masked
        assert "XXXX-XXXX-1234" in masked
        assert "ABCPM1234D" not in masked
        assert "XXXXX1234X" in masked

    def test_regex_synthesis_helper(self):
        assert synthesize_regex_for_value("2026-05-15") == r"\b\d{4}-\d{2}-\d{2}\b"
        assert synthesize_regex_for_value("15/06/1991") == r"\b\d{2}/\d{2}/\d{4}\b"
        assert synthesize_regex_for_value("INV-2026-9901") == r"\b[A-Z0-9]+(?:-[A-Z0-9]+)+\b"

    def test_schema_learning_lifecycle_and_versioning(self, app):
        with app.app_context():
            db_path = app.config["DATABASE_PATH"]
            doc_id = "DOC-LEARN-001"

            # 1. Seed a document with raw text containing an anchor phrase
            insert_document({
                "id": doc_id,
                "original_filename": "invoice_sample.pdf",
                "document_type": "commercial_invoice",
                "mime_type": "application/pdf",
                "processing_status": "completed",
                "review_status": "approved"
            }, db_path=db_path)

            from backend.database.db import get_db_connection
            conn = get_db_connection(db_path)
            cur = conn.cursor()
            cur.execute("""
                UPDATE documents
                SET extracted_text = 'TAX INVOICE\nTax Identification Number: US-EIN-881290\nTotal Due: USD 45,000.00\nPayment Due Date: 2026-07-31'
                WHERE id = ?;
            """, (doc_id,))
            conn.commit()
            conn.close()

            # 2. Seed employee-confirmed attributes
            insert_extracted_attribute({
                "document_id": doc_id,
                "attribute_key": "tax_id",
                "attribute_label": "Tax Identification Number",
                "data_type": "string",
                "raw_value": "US-EIN-881290",
                "normalized_value": "US-EIN-881290",
                "confidence": 1.0,
                "source_type": "custom",
                "is_verified": True
            }, db_path=db_path)

            insert_extracted_attribute({
                "document_id": doc_id,
                "attribute_key": "payment_due_date",
                "attribute_label": "Payment Due Date",
                "data_type": "date",
                "raw_value": "2026-07-31",
                "normalized_value": "2026-07-31",
                "confidence": 1.0,
                "source_type": "custom",
                "is_verified": True
            }, db_path=db_path)

            # 3. Learn Schema v1
            schema_v1 = SchemaLearner.learn_schema_for_type("commercial_invoice", db_path=db_path)
            assert schema_v1["version"] == 1
            assert schema_v1["attribute_count"] >= 2
            assert "tax_id" in schema_v1["anchor_phrases"]
            assert any("Tax Identification Number" in a for a in schema_v1["anchor_phrases"]["tax_id"])

            # 4. Verify Active Schema
            active_schema = SchemaLearner.get_active_schema("commercial_invoice", db_path=db_path)
            assert active_schema is not None
            assert active_schema["version"] == 1
            assert bool(active_schema["is_active"]) is True

            # 5. Learn Schema v2 (progression)
            schema_v2 = SchemaLearner.learn_schema_for_type("commercial_invoice", db_path=db_path)
            assert schema_v2["version"] == 2

            versions = SchemaLearner.list_schema_versions("commercial_invoice", db_path=db_path)
            assert len(versions) == 2
            assert versions[0]["version"] == 2 and bool(versions[0]["is_active"]) is True
            assert versions[1]["version"] == 1 and bool(versions[1]["is_active"]) is False

            # 6. Rollback to Version 1
            rolled_back = SchemaLearner.rollback_schema("commercial_invoice", target_version=1, db_path=db_path)
            assert rolled_back is True

            active_after_rollback = SchemaLearner.get_active_schema("commercial_invoice", db_path=db_path)
            assert active_after_rollback["version"] == 1
            assert bool(active_after_rollback["is_active"]) is True


class TestInContextExtractionImprovement:
    """Verifies that learned schema anchors and regexes extract custom fields without fine-tuning."""

    def test_learned_schema_extracts_custom_attribute(self):
        learned_schema = {
            "version": 1,
            "attribute_definitions": [
                {
                    "attribute_key": "tax_id",
                    "display_label": "Tax Identification Number",
                    "data_type": "string",
                    "regex_pattern": r"\b[A-Z0-9]+(?:-[A-Z0-9]+)+\b"
                }
            ],
            "anchor_phrases": {
                "tax_id": ["Tax Identification Number:", "Tax ID:"]
            },
            "regex_patterns": {
                "tax_id": r"\b[A-Z0-9]+(?:-[A-Z0-9]+)+\b"
            }
        }

        sample_text = "BILL TO CUSTOMER\nTax Identification Number: US-EIN-992011\nAmount Due: $1,200.00"

        # FieldExtractor uses learned schema
        extracted = FieldExtractor.extract_fields(sample_text, document_type="commercial_invoice", learned_schema=learned_schema)
        extra_attrs = extracted.get("extra_fields", {}).get("attributes", [])
        tax_matches = [a for a in extra_attrs if a.get("attribute_key") == "tax_id"]

        assert len(tax_matches) == 1
        assert "US-EIN-992011" in tax_matches[0]["attribute_value"]
        assert tax_matches[0]["source_type"] == "learned_schema"


class TestDatasetEvaluationMetrics:
    """Evaluates accuracy, precision, recall, F1, and CER over the authorized 10-person dataset."""

    def test_levenshtein_and_cer_metrics(self):
        assert levenshtein_distance("AARAV", "AARAV") == 0
        assert levenshtein_distance("AARAV", "AARAU") == 1
        assert compute_cer("AARAV", "AARAV") == 0.0
        assert compute_cer("AARAV", "AARAU") == 0.2

    def test_evaluate_synthetic_10_applicant_dataset(self, app):
        with app.app_context():
            db_path = app.config["DATABASE_PATH"]
            eval_report = DatasetEvaluator.evaluate_synthetic_dataset(db_path=db_path)

            summary = eval_report["summary"]
            assert summary["total_applicants"] == 10
            assert summary["total_documents"] == 25
            assert summary["classification_accuracy"] >= 0.90, "Classification accuracy must meet 90%+ benchmark"
            assert summary["validation_accuracy"] >= 0.80, "Validation status accuracy must meet 80%+ benchmark"
            assert summary["overall_precision"] >= 0.85
            assert summary["overall_recall"] >= 0.80
            assert summary["overall_f1_score"] >= 0.80
            assert summary["mean_character_error_rate"] <= 0.15, "Mean CER must be <= 15%"

            # Verify privacy compliance
            assert eval_report["privacy_compliance"]["pii_masked"] is True
            assert eval_report["privacy_compliance"]["unauthorized_data_used"] is False


class TestSchemaAndEvaluationRestAPI:
    """Tests /api/v1/schemas and /api/v1/evaluation endpoints."""

    def test_schema_api_endpoints(self, client, app, admin_key):
        with app.app_context():
            db_path = app.config["DATABASE_PATH"]
            # Seed a sample document
            insert_document({
                "id": "DOC-API-001",
                "original_filename": "salary_sample.pdf",
                "document_type": "salary_slip",
                "processing_status": "completed",
                "review_status": "approved"
            }, db_path=db_path)

        headers = {"X-API-Key": admin_key}

        # 1. Learn schema via POST
        learn_res = client.post("/api/v1/schemas/salary_slip/learn", headers=headers)
        assert learn_res.status_code == 201
        data = learn_res.get_json()
        assert data["success"] is True
        assert data["schema"]["version"] == 1

        # 2. Get active schema via GET
        get_res = client.get("/api/v1/schemas/salary_slip", headers=headers)
        assert get_res.status_code == 200
        assert get_res.get_json()["schema"]["version"] == 1

        # 3. List versions
        ver_res = client.get("/api/v1/schemas/salary_slip/versions", headers=headers)
        assert ver_res.status_code == 200
        assert ver_res.get_json()["total_versions"] >= 1

    def test_evaluation_benchmark_api(self, client, admin_key):
        headers = {"X-API-Key": admin_key}
        res = client.get("/api/v1/evaluation/benchmark", headers=headers)
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        summary = data["benchmark"]["summary"]
        assert summary["total_documents"] == 25
        assert summary["overall_f1_score"] > 0.70
