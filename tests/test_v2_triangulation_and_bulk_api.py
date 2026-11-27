import io
import time
import json
import base64
import pytest
from flask import Flask
from backend.app import create_app
from backend.database.db import (
    init_db,
    create_api_key,
    get_document,
    get_applicant,
    get_batch_submission,
    get_batch_documents,
    get_applicant_triangulation
)
from backend.services.triangulation_rule_service import (
    TriangulationRuleService,
    get_canonical_combination_key,
    parse_combination_key
)
from backend.services.comparator import CrossDocumentComparator
from backend.services.webhook_dispatcher import WebhookDispatcher


@pytest.fixture
def app(tmp_path):
    """Create isolated test application instance."""
    test_db = str(tmp_path / "test_triangulation_v2.db")
    app = create_app("testing")
    app.config["DATABASE_PATH"] = test_db
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    app.config["PROCESSED_FOLDER"] = str(tmp_path / "processed")
    app.config["TESTING"] = True
    app.config["AI_PROVIDER"] = "mock"

    with app.app_context():
        init_db(test_db)
        # Seed default policies
        TriangulationRuleService.seed_default_configurations()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_key(app):
    with app.app_context():
        db_path = app.config["DATABASE_PATH"]
        raw_key, record = create_api_key(
            name="Test Enterprise Key",
            permissions=["documents:read", "documents:write", "verification:review", "admin"],
            db_path=db_path
        )
        return raw_key


class TestTriangulationRuleService:
    """Test policy key generation, rule discovery, versioning and rollback."""

    def test_canonical_combination_key(self):
        assert get_canonical_combination_key(["pan", "aadhaar"]) == "aadhaar+pan"
        assert get_canonical_combination_key(["PAN", "AADHAAR"]) == "aadhaar+pan"
        assert get_canonical_combination_key(["passport", "aadhaar", "pan"]) == "aadhaar+pan+passport"
        assert parse_combination_key("aadhaar+pan") == ["aadhaar", "pan"]

    def test_ai_rule_discovery_recommends_expected_policies(self, app):
        with app.app_context():
            discovery = TriangulationRuleService.discover_rules_for_combination(["aadhaar", "pan"])
            assert discovery["total_rules_discovered"] > 0
            rules = discovery["rules"]

            # Name and DOB should be COMPARE
            name_rule = next((r for r in rules if r.get("concept") == "name"), None)
            assert name_rule is not None
            assert name_rule["recommendation"] == "COMPARE"
            assert name_rule["is_enabled"] is True

            dob_rule = next((r for r in rules if r.get("concept") == "dob"), None)
            assert dob_rule is not None
            assert dob_rule["recommendation"] == "COMPARE"

            # Incompatible identifiers (PAN vs Aadhaar) should be NOT_RECOMMENDED
            incompat_rule = next((r for r in rules if r.get("recommendation") == "NOT_RECOMMENDED"), None)
            assert incompat_rule is not None
            assert incompat_rule["is_enabled"] is False

    def test_rule_versioning_and_rollback(self, app):
        with app.app_context():
            config = TriangulationRuleService.get_or_create_configuration("aadhaar+pan")
            initial_v = config["active_version"]

            # Save Version 2
            v2_rules = [
                {
                    "id": "rule_name_custom",
                    "concept": "name",
                    "source_doc_type": "aadhaar",
                    "source_attribute": "name",
                    "source_label": "Name",
                    "target_doc_type": "pan",
                    "target_attribute": "name",
                    "target_label": "Name",
                    "recommendation": "COMPARE",
                    "explanation": "Strict compliance name cross-check",
                    "normalization": "exact",
                    "is_enabled": True
                }
            ]
            saved = TriangulationRuleService.save_new_rule_version(
                configuration_id=config["id"],
                attribute_rules=v2_rules,
                published_by="Senior Risk Officer",
                change_summary="Strict exact match on name"
            )
            assert saved["version"] == initial_v + 1

            active_info = TriangulationRuleService.get_active_rules("aadhaar+pan")
            assert active_info["active_version"] == saved["version"]
            assert len(active_info["rules"]) == 1

            # Rollback to Version 1
            rolled = TriangulationRuleService.rollback_version(config["id"], initial_v)
            assert rolled["active_version"] == initial_v

            active_after_rollback = TriangulationRuleService.get_active_rules("aadhaar+pan")
            assert active_after_rollback["active_version"] == initial_v


class TestVerificationEngineRuleEnforcement:
    """Test that disabled rules are strictly excluded and missing fields are not mismatches."""

    def test_disabled_rules_strictly_excluded_from_execution(self, app):
        with app.app_context():
            config = TriangulationRuleService.get_or_create_configuration("aadhaar+pan")
            
            # Disable DOB comparison in active policy
            modified_rules = [
                {
                    "id": "rule_name",
                    "concept": "name",
                    "source_doc_type": "aadhaar",
                    "source_attribute": "name",
                    "target_doc_type": "pan",
                    "target_attribute": "name",
                    "recommendation": "COMPARE",
                    "explanation": "Name check",
                    "normalization": "normalized_text",
                    "is_enabled": True
                },
                {
                    "id": "rule_dob_disabled",
                    "concept": "dob",
                    "source_doc_type": "aadhaar",
                    "source_attribute": "dob",
                    "target_doc_type": "pan",
                    "target_attribute": "dob",
                    "recommendation": "COMPARE",
                    "explanation": "DOB check disabled for this test",
                    "normalization": "date_iso",
                    "is_enabled": False  # DISABLED
                }
            ]
            TriangulationRuleService.save_new_rule_version(
                configuration_id=config["id"],
                attribute_rules=modified_rules,
                published_by="Test Admin",
                change_summary="Disabled DOB rule"
            )

            # Two documents with matching names but conflicting DOBs
            docs = [
                {
                    "id": "d1",
                    "applicant_id": "APPL-TEST-001",
                    "type": "pan",
                    "filename": "pan.pdf",
                    "fields": {"name": "Rajesh Kumar", "dob": "1980-01-01", "id_number": "ABCDE1234F"}
                },
                {
                    "id": "d2",
                    "applicant_id": "APPL-TEST-001",
                    "type": "aadhaar",
                    "filename": "aadhaar.pdf",
                    "fields": {"name": "Rajesh Kumar", "dob": "1985-05-05", "id_number": "9876 5432 1098"}
                }
            ]

            result = CrossDocumentComparator.compare_applicant_documents(
                documents=docs,
                applicant_name="Rajesh Kumar",
                applicant_id="APPL-TEST-001"
            )

            # Because DOB rule is disabled, the DOB conflict must NOT trigger a discrepancy!
            assert not any("dob mismatch" in str(d).lower() for d in result.get("discrepancies", []))
            
            # Matrix row for DOB must reflect NOT_EXECUTED
            dob_row = next((r for r in result["matrix"]["rows"] if r["attribute_key"] == "dob"), None)
            assert dob_row is not None
            assert dob_row["result_status"] == "NOT_EXECUTED"

    def test_missing_data_not_treated_as_mismatch(self, app):
        with app.app_context():
            docs = [
                {
                    "id": "d1",
                    "applicant_id": "APPL-TEST-002",
                    "type": "pan",
                    "filename": "pan.pdf",
                    "fields": {"name": "Meera Rao", "dob": "1992-04-10"}
                },
                {
                    "id": "d2",
                    "applicant_id": "APPL-TEST-002",
                    "type": "driving_licence",
                    "filename": "dl.pdf",
                    "fields": {"name": "Meera Rao"}  # DOB is missing on DL
                }
            ]

            result = CrossDocumentComparator.compare_applicant_documents(
                documents=docs,
                applicant_name="Meera Rao",
                applicant_id="APPL-TEST-002"
            )

            # Missing DOB on DL is not a mismatch
            assert not any("mismatch" in str(d).lower() for d in result.get("discrepancies", []))
            assert result["overall_verdict"] in ("VERIFIED", "MANUAL_REVIEW")


class TestEnterpriseBulkBase64API:
    """Test REST API bulk Base64 batch submission, polling, verification, and webhooks."""

    def test_readiness_probe(self, client):
        res = client.get("/api/v1/ready")
        assert res.status_code == 200
        data = res.get_json()
        assert data["ready"] is True
        assert data["checks"]["database"]["status"] == "ok"

    def test_submit_bulk_base64_batch_and_track_status(self, client, admin_key):
        # 1x1 transparent PNG Base64
        tiny_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

        payload = {
            "source_system": "HRMS_PORTAL",
            "external_applicant_reference": "EMP-94812",
            "external_application_reference": "APP-2026-X1",
            "applicant_name": "Kavita Raman",
            "idempotency_key": "IDEM-TEST-101",
            "documents": [
                {
                    "external_document_reference": "DOC-REF-01",
                    "file_name": "kavita_pan.png",
                    "mime_type": "image/png",
                    "specified_document_type": "pan",
                    "content_base64": tiny_png_b64
                },
                {
                    "external_document_reference": "DOC-REF-02",
                    "file_name": "kavita_aadhaar.png",
                    "mime_type": "image/png",
                    "specified_document_type": "aadhaar",
                    "content_base64": tiny_png_b64
                }
            ]
        }

        # 1. Submit batch
        res = client.post(
            "/api/v1/batches",
            headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
            json=payload
        )
        assert res.status_code == 202
        data = res.get_json()
        assert data["success"] is True
        assert data["batch_id"].startswith("BATCH-")
        assert data["accepted_documents"] == 2
        batch_id = data["batch_id"]
        applicant_id = data["applicant_id"]

        # 2. Idempotency replay check
        replay_res = client.post(
            "/api/v1/batches",
            headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
            json=payload
        )
        assert replay_res.status_code == 200
        assert replay_res.get_json()["idempotent_replay"] is True

        # 3. Poll batch status
        status_res = client.get(
            f"/api/v1/batches/{batch_id}",
            headers={"X-API-Key": admin_key}
        )
        assert status_res.status_code == 200
        status_data = status_res.get_json()
        assert status_data["batch_id"] == batch_id
        assert status_data["total_documents"] == 2

        # 4. Trigger verification
        verif_res = client.post(
            f"/api/v1/batches/{batch_id}/verification",
            headers={"X-API-Key": admin_key}
        )
        assert verif_res.status_code == 200
        verif_data = verif_res.get_json()
        assert verif_data["success"] is True
        assert "overall_verdict" in verif_data
        assert "consistency_score" in verif_data

        # 5. Fetch applicant verification summary
        summary_res = client.get(
            f"/api/v1/applicants/{applicant_id}/verification",
            headers={"X-API-Key": admin_key}
        )
        assert summary_res.status_code == 200
        summary_data = summary_res.get_json()
        assert summary_data["applicant_id"] == applicant_id
        assert "overall_verdict" in summary_data
        assert "matrix" in summary_data

    def test_webhook_hmac_signature_verification(self):
        secret = "super_secret_webhook_key_2026"
        payload_bytes = b'{"event":"batch.completed","data":{"batch_id":"BATCH-01"}}'
        sig = WebhookDispatcher.compute_signature(secret, payload_bytes)
        sig_header = f"sha256={sig}"

        assert WebhookDispatcher.verify_signature(secret, payload_bytes, sig_header) is True
        assert WebhookDispatcher.verify_signature(secret, b'tampered payload', sig_header) is False
