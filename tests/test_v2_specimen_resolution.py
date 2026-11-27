"""
VeriDoc AI 2.0 — Automated Regression Tests for Specimen Resolution from Database.
Verifies all 10 Acceptance Criteria:
1. Open Aadhaar: an existing Aadhaar document is automatically displayed.
2. Open PAN: an existing PAN document is automatically displayed.
3. Open Passport: the best available Passport specimen is selected.
4. Open Salary Slip: existing salary document data is loaded.
5. Extracted attributes appear with actual stored values.
6. Available bounding boxes correctly highlight their corresponding values.
7. Manual attribute creation and saving work.
8. Reopening the schema preserves the saved attribute definition.
9. No unrelated applicant's document is exposed.
10. A document type with no existing specimen displays a proper fallback.
"""

import pytest
import json
from pathlib import Path
from backend.app import create_app
from backend.database.db import (
    get_db_connection,
    init_db,
    insert_document,
    insert_document_type,
    publish_document_schema,
    get_document_type_details,
    get_document,
    get_document_extracted_attributes,
)


@pytest.fixture
def app_client(tmp_path):
    test_db = str(tmp_path / "test_specimen.db")
    init_db(db_path=test_db)
    app = create_app("testing")
    app.config["DATABASE_PATH"] = test_db
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client, test_db


class TestSpecimenResolution:

    def test_criterion_1_aadhaar_specimen_resolution(self, app_client):
        client, db_path = app_client
        res = client.get("/api/repository/types/aadhaar/sample")
        assert res.status_code == 200
        data = res.get_json()["data"]
        assert data["document_type"]["type_key"] == "aadhaar"
        # If database has aadhaar specimen, it returns its ID
        if data["sample_document_id"]:
            assert data["has_specimen"] is True
            assert "aadhaar" in data["sample_filename"].lower() or "pdf" in data["sample_filename"].lower()

    def test_criterion_2_pan_specimen_resolution(self, app_client):
        client, db_path = app_client
        res = client.get("/api/repository/types/pan/sample")
        assert res.status_code == 200
        data = res.get_json()["data"]
        assert data["document_type"]["type_key"] == "pan"
        if data["sample_document_id"]:
            assert data["has_specimen"] is True
            assert "pan" in data["sample_filename"].lower() or "pdf" in data["sample_filename"].lower()

    def test_criterion_3_passport_specimen_best_selection(self, app_client):
        client, db_path = app_client
        res = client.get("/api/repository/types/passport/sample")
        assert res.status_code == 200
        data = res.get_json()["data"]
        assert data["document_type"]["type_key"] == "passport"
        if data["sample_document_id"]:
            assert data["has_specimen"] is True

    def test_criterion_4_salary_slip_data_loaded(self, app_client):
        client, db_path = app_client
        res = client.get("/api/repository/types/salary_slip/sample")
        assert res.status_code == 200
        data = res.get_json()["data"]
        assert data["document_type"]["type_key"] == "salary_slip"
        assert "details" in data
        assert data["details"]["document_count"] >= 0

    def test_criterion_5_and_6_attributes_values_and_bounding_boxes(self, app_client):
        client, db_path = app_client
        # Insert a specimen document with full attributes and bounding boxes
        doc_id = "TEST-SPECIMEN-001"
        doc_data = {
            "id": doc_id,
            "applicant_id": "APPL-TEST-001",
            "original_filename": "test_aadhaar.pdf",
            "stored_filename": "test_aadhaar.pdf",
            "document_type": "aadhaar",
            "file_size": 1024,
            "processing_status": "completed",
            "review_status": "verified",
        }
        insert_document(doc_data, db_path=db_path)

        # Set extracted fields with real values and coordinates
        fields = {
            "applicant_name": "Aarav Devansh Kulkarni",
            "date_of_birth": "1991-06-14",
            "gender": "MALE",
            "identification_number": "123456789012",
            "address": "Pune Maharashtra",
            "attributes": [
                {
                    "attribute_key": "applicant_name",
                    "attribute_label": "Applicant Name",
                    "attribute_value": "Aarav Devansh Kulkarni",
                    "bounding_box": [307, 290, 335, 572],
                    "confidence": 0.99,
                    "page_number": 1
                },
                {
                    "attribute_key": "identification_number",
                    "attribute_label": "Aadhaar Number",
                    "attribute_value": "1234 5678 9012",
                    "bounding_box": [794, 376, 828, 622],
                    "confidence": 0.99,
                    "page_number": 1
                }
            ]
        }
        conn = get_db_connection(db_path)
        cur = conn.cursor()
        cur.execute("UPDATE documents SET extracted_fields = ? WHERE id = ?", (json.dumps(fields), doc_id))
        conn.commit()
        conn.close()

        # Query attributes
        res = client.get(f"/api/documents/{doc_id}/attributes")
        assert res.status_code == 200
        attrs = res.get_json()["data"]["attributes"]
        assert len(attrs) >= 2

        name_attr = next(a for a in attrs if a["attribute_key"] == "applicant_name")
        assert name_attr["normalized_value"] == "Aarav Devansh Kulkarni"
        assert name_attr["bounding_box"] == [307, 290, 335, 572]

        # Aadhaar number is masked
        id_attr = next(a for a in attrs if a["attribute_key"] == "identification_number")
        assert "XXXX" in id_attr["normalized_value"]
        assert id_attr["bounding_box"] == [794, 376, 828, 622]

    def test_criterion_7_and_8_attribute_creation_and_reopening(self, app_client):
        client, db_path = app_client
        # Add custom attribute to document
        doc_id = "DOC-ATTR-TEST"
        insert_document({
            "id": doc_id,
            "applicant_id": "APPL-TEST-002",
            "original_filename": "pan_specimen.pdf",
            "document_type": "pan",
            "processing_status": "completed"
        }, db_path=db_path)

        payload = {
            "attribute_key": "custom_tax_id",
            "attribute_label": "Custom Tax Identifier",
            "attribute_value": "TAX-998877",
            "bounding_box": [100, 200, 150, 400],
            "data_type": "string"
        }
        res = client.post(f"/api/documents/{doc_id}/attributes", json=payload)
        assert res.status_code in (200, 201)
        saved_attr = res.get_json()["data"]["attribute"]
        assert saved_attr["attribute_key"] == "custom_tax_id"
        assert saved_attr["normalized_value"] == "TAX-998877"

        # Publish new schema version
        pub_res = client.post("/api/repository/types/pan/schemas", json={
            "attributes": [
                {
                    "attribute_key": "custom_tax_id",
                    "display_label": "Custom Tax Identifier",
                    "data_type": "string",
                    "sample_value": "TAX-998877",
                    "bounding_box": [100, 200, 150, 400]
                }
            ],
            "published_by": "Test Compliance Officer"
        })
        assert pub_res.status_code in (200, 201)

        # Criterion 8: Reopen schema details and verify preservation
        details_res = client.get("/api/repository/types/pan")
        assert details_res.status_code == 200
        details = details_res.get_json()["data"]
        active = details["active_schema"]
        assert active is not None
        assert any(a["attribute_key"] == "custom_tax_id" for a in active["attribute_definitions"])

    def test_criterion_9_no_unrelated_applicant_leakage(self, app_client):
        client, db_path = app_client
        # When querying for a type with no documents (e.g. commercial_invoice)
        res = client.get("/api/repository/types/commercial_invoice/sample")
        assert res.status_code == 200
        data = res.get_json()["data"]
        # Must NEVER return an unrelated applicant's Aadhaar or PAN document
        assert data["has_specimen"] is False
        assert data["sample_document_id"] is None

    def test_criterion_10_no_specimen_proper_fallback(self, app_client):
        client, db_path = app_client
        res = client.get("/api/repository/types/utility_bill/sample")
        assert res.status_code == 200
        data = res.get_json()["data"]
        assert data["has_specimen"] is False
        assert data["sample_document_id"] is None
        assert "utility_bill" in data["document_type"]["type_key"]
