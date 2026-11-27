"""
VeriDoc AI 2.0 — Universal Document Type Creation & AI Identification Test Suite

Tests:
1. Listing catalog document types (GET /api/documents/types)
2. Sample-based document type and attribute discovery (POST /api/documents/discover-type)
3. Invalid sample uploads rejection (POST /api/documents/discover-type)
4. Confirming and registering a new document type with Schema v1 (POST /api/documents/register-type)
5. Validation guards for type registration (invalid slug, empty attributes)
6. Processing documents under the newly registered custom document type
7. AI Identification workflow for unfamiliar documents with unregistered type detection
8. Schema reuse for subsequent documents of the newly registered type
"""

import io
import json
import pytest
import pymupdf
from pathlib import Path

from backend.app import create_app
from backend.database.db import (
    init_db,
    get_document_type,
    get_document_schema,
    list_document_types,
)
from backend.services.schema_learner import SchemaLearner


@pytest.fixture
def app(tmp_path):
    test_db = str(tmp_path / "test_universal.db")
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


def _create_sample_trade_license_pdf(file_path: Path) -> None:
    """Create a sample synthetic Trade License PDF document."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)

    page.insert_text((50, 80), "MUNICIPAL CORPORATION OF GREATER MUMBAI", fontsize=14)
    page.insert_text((50, 110), "COMMERCIAL ESTABLISHMENT TRADE LICENCE", fontsize=16)
    page.insert_text((50, 160), "Licence Number: TL-MH-2026-9812", fontsize=12)
    page.insert_text((50, 200), "Trade Category: Restaurant & Food Services", fontsize=12)
    page.insert_text((50, 240), "Business Name: Powai Hospitality Ventures", fontsize=12)
    page.insert_text((50, 280), "Issue Date: 2026-04-01", fontsize=12)
    page.insert_text((50, 320), "Annual Licence Fee: INR 45,000.00", fontsize=12)
    page.insert_text((50, 360), "Validity Period: 2026-04-01 to 2027-03-31", fontsize=12)

    doc.save(str(file_path))
    doc.close()


class TestUniversalDocumentTypeCreation:
    """Verifies end-to-end creation, discovery, and processing of new document types."""

    def test_get_document_types_endpoint(self, client):
        """Verify GET /api/documents/types returns registered catalog document types."""
        res = client.get("/api/documents/types")
        assert res.status_code == 200
        data = res.get_json()["data"]
        types = data["types"]
        assert len(types) >= 10
        type_keys = [t["type_key"] for t in types]
        assert "pan" in type_keys
        assert "commercial_invoice" in type_keys
        assert "utility_bill" in type_keys

    def test_discover_document_type_from_sample(self, client, tmp_path):
        """Verify sample PDF analysis discovers attributes and bounding boxes."""
        sample_path = tmp_path / "sample_trade_license.pdf"
        _create_sample_trade_license_pdf(sample_path)

        with open(sample_path, "rb") as f:
            pdf_bytes = f.read()

        data = {
            "files": (io.BytesIO(pdf_bytes), "sample_trade_license.pdf", "application/pdf")
        }
        res = client.post("/api/documents/discover-type", data=data, content_type="multipart/form-data")
        assert res.status_code == 200
        resp_data = res.get_json()["data"]

        assert "sample_trade_license.pdf" in resp_data["sample_filenames"]
        assert len(resp_data["sample_text_preview"]) > 50

        discovered = resp_data["discovered_attributes"]
        assert len(discovered) >= 3

        keys = [a["attribute_key"] for a in discovered]
        # Should discover key-value patterns from the sample PDF
        assert any("licence_number" in k or "number" in k for k in keys)
        assert any("trade_category" in k or "category" in k or "business_name" in k for k in keys)

        # Verify attribute schema structure
        for attr in discovered:
            assert "attribute_key" in attr
            assert "attribute_label" in attr
            assert "sample_value" in attr
            assert attr["source_type"] == "discovered"
            assert attr["confidence"] > 0.7

    def test_discover_document_type_invalid_upload(self, client):
        """Verify 400 error when sample discovery is invoked without valid files."""
        res = client.post("/api/documents/discover-type", data={}, content_type="multipart/form-data")
        assert res.status_code == 400
        assert res.get_json()["success"] is False

    def test_register_new_document_type_and_schema_v1(self, client, app):
        """Verify registering a new document type creates catalog definition and Schema v1."""
        payload = {
            "type_key": "trade_license",
            "display_name": "Municipal Trade License",
            "category": "business",
            "description": "Commercial establishment operating trade license",
            "attribute_definitions": [
                {
                    "attribute_key": "licence_number",
                    "attribute_label": "Licence Number",
                    "sample_value": "TL-MH-2026-9812",
                    "data_type": "string",
                    "required": True,
                    "regex_pattern": r"\bTL-[A-Z]{2}-\d{4}-\d+\b"
                },
                {
                    "attribute_key": "business_name",
                    "attribute_label": "Business Name",
                    "sample_value": "Powai Hospitality Ventures",
                    "data_type": "string",
                    "required": True
                },
                {
                    "attribute_key": "licence_fee",
                    "attribute_label": "Licence Fee",
                    "sample_value": "INR 45,000.00",
                    "data_type": "currency",
                    "required": False
                }
            ],
            "sample_text": "MUNICIPAL CORPORATION\nLicence Number: TL-MH-2026-9812\nBusiness Name: Powai Hospitality Ventures"
        }

        res = client.post("/api/documents/register-type", json=payload)
        assert res.status_code == 201
        data = res.get_json()["data"]

        doc_type = data["document_type"]
        assert doc_type["type_key"] == "trade_license"
        assert doc_type["display_name"] == "Municipal Trade License"

        schema = data["schema"]
        assert schema["version"] == 1
        assert schema["attribute_count"] == 3
        assert "licence_number" in schema["anchor_phrases"]
        assert "licence_number" in schema["regex_patterns"]

        # Verify persisted in database
        db_path = app.config["DATABASE_PATH"]
        stored_type = get_document_type("trade_license", db_path=db_path)
        assert stored_type is not None
        assert stored_type["type_key"] == "trade_license"

        active_schema = SchemaLearner.get_active_schema("trade_license", db_path=db_path)
        assert active_schema is not None
        assert active_schema["version"] == 1
        assert len(active_schema["few_shot_examples"]) == 1

    def test_register_document_type_validation_guards(self, client):
        """Verify rejection of invalid slug keys or empty attribute lists."""
        # 1. Invalid slug key (contains uppercase / spaces / symbols)
        bad_key_res = client.post("/api/documents/register-type", json={
            "type_key": "Invalid Type Key!",
            "display_name": "Invalid Type",
            "attribute_definitions": [{"attribute_key": "field1"}]
        })
        assert bad_key_res.status_code == 400
        assert "Invalid type_key" in bad_key_res.get_json()["message"]

        # 2. Empty attribute definitions
        empty_attr_res = client.post("/api/documents/register-type", json={
            "type_key": "valid_key",
            "display_name": "Valid Name",
            "attribute_definitions": []
        })
        assert empty_attr_res.status_code == 400
        assert "attribute_definitions is required" in empty_attr_res.get_json()["message"]

    def test_upload_and_schema_reuse_for_custom_type(self, client, app, tmp_path):
        """
        End-to-End Test:
        1. Register 'equipment_lease' type.
        2. Upload a sample document specifying document_type = 'equipment_lease'.
        3. Verify processing pipeline applies learned schema and extracts the custom attributes.
        """
        # 1. Register type
        reg_payload = {
            "type_key": "equipment_lease",
            "display_name": "Equipment Lease Agreement",
            "category": "legal",
            "description": "Heavy machinery and equipment lease contracts",
            "attribute_definitions": [
                {
                    "attribute_key": "lease_id",
                    "attribute_label": "Lease Agreement ID",
                    "sample_value": "EQ-LEASE-2026-09",
                    "data_type": "string"
                },
                {
                    "attribute_key": "monthly_rent",
                    "attribute_label": "Monthly Rental Amount",
                    "sample_value": "USD 8,500.00",
                    "data_type": "currency"
                }
            ]
        }
        reg_res = client.post("/api/documents/register-type", json=reg_payload)
        assert reg_res.status_code == 201

        # 2. Create document PDF
        pdf_path = tmp_path / "lease_contract_01.pdf"
        doc = pymupdf.open()
        p = doc.new_page(width=600, height=800)
        p.insert_text((50, 100), "EQUIPMENT LEASE AGREEMENT", fontsize=16)
        p.insert_text((50, 150), "Lease Agreement ID: EQ-LEASE-2026-09", fontsize=12)
        p.insert_text((50, 200), "Monthly Rental Amount: USD 8,500.00", fontsize=12)
        doc.save(str(pdf_path))
        doc.close()

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # 3. Upload with specified document_type
        upload_data = {
            "files": (io.BytesIO(pdf_bytes), "lease_contract_01.pdf", "application/pdf"),
            "document_type": "equipment_lease",
            "applicant_id": "APPL-CORP-01"
        }
        up_res = client.post("/api/documents/upload", data=upload_data, content_type="multipart/form-data")
        assert up_res.status_code == 201
        uploaded_doc = up_res.get_json()["data"]["uploaded"][0]
        assert uploaded_doc["document_type"] == "equipment_lease"

        # 4. Process document
        doc_id = uploaded_doc["id"]
        proc_res = client.post(f"/api/documents/{doc_id}/process")
        assert proc_res.status_code == 200
        proc_data = proc_res.get_json()["data"]["result"]

        assert proc_data["classification"]["classified_type"] == "equipment_lease"
        assert proc_data["classification"]["is_user_specified"] is True

        # Verify custom attributes were extracted via learned schema
        attrs = proc_data["extracted_fields"].get("attributes", [])
        attr_keys = [a["attribute_key"] for a in attrs]
        assert "lease_id" in attr_keys or "lease_agreement_id" in attr_keys or any("lease" in k for k in attr_keys)

    def test_ai_identify_workflow_unfamiliar_document(self, client, app, tmp_path):
        """
        Verify AI identification workflow when document is uploaded without type specification:
        1. Uploads an unfamiliar document with document_type='auto'.
        2. Processor classifies automatically.
        3. Flags is_unregistered_type = True when type cannot be classified into catalog.
        """
        # Create an unfamiliar certificate
        cert_path = tmp_path / "fire_safety_cert.pdf"
        doc = pymupdf.open()
        p = doc.new_page(width=600, height=800)
        p.insert_text((50, 100), "STATE FIRE SERVICE DEPARTMENT", fontsize=14)
        p.insert_text((50, 140), "NO OBJECTION CERTIFICATE (NOC)", fontsize=16)
        p.insert_text((50, 190), "NOC Certificate Number: FS-NOC-2026-441", fontsize=12)
        p.insert_text((50, 230), "Inspection Status: Approved Compliant", fontsize=12)
        doc.save(str(cert_path))
        doc.close()

        with open(cert_path, "rb") as f:
            pdf_bytes = f.read()

        # Upload with document_type='auto'
        upload_data = {
            "files": (io.BytesIO(pdf_bytes), "fire_safety_cert.pdf", "application/pdf"),
            "document_type": "auto",
            "applicant_id": "APPL-BLDG-02"
        }
        up_res = client.post("/api/documents/upload", data=upload_data, content_type="multipart/form-data")
        assert up_res.status_code == 201
        doc_id = up_res.get_json()["data"]["uploaded"][0]["id"]

        proc_res = client.post(f"/api/documents/{doc_id}/process")
        assert proc_res.status_code == 200
        proc_data = proc_res.get_json()["data"]["result"]

        # Classification should run and identify unregistered / unknown status
        cls = proc_data["classification"]
        assert "is_unregistered_type" in cls
        assert "suggest_register_type" in cls
        assert cls["is_unregistered_type"] is True
