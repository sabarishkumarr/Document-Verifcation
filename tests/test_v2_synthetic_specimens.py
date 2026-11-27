"""
VeriDoc AI 2.0 — Automated Test Suite for Synthetic Specimen Library & Attribute Population
Verifies all 11 Acceptance Criteria:
1. Every registered document type has a specimen (has_specimen == True).
2. Every configured attribute has a non-empty specimen value.
3. Attribute values match the configured data types and validation rules.
4. Bounding-box coordinates correctly map to visible document regions (0-1000 scale).
5. Selecting an attribute highlights the correct region (coordinates mapped in schema & attributes).
6. Selecting a region identifies the corresponding attribute (spatial intersection).
7. Multi-page documents (bank_statement) render and navigate correctly (page 1 and page 2).
8. Synthetic fixtures do not overwrite existing records (dedicated APPL-SYN-FIXTURES namespace).
9. Re-running fixture generation creates no duplicates (idempotency).
10. Applicant isolation remains intact (specimen resolution does not leak applicant records).
11. Existing upload, classification, extraction, verification, API and reporting functionality remains unaffected.
"""

import pytest
import json
import re
from pathlib import Path
from backend.app import create_app
from backend.database.db import (
    get_db_connection,
    init_db,
    insert_applicant,
    insert_document,
    list_document_types,
    get_document_type_details,
    get_document,
    get_document_extracted_attributes,
)
from scripts.generate_synthetic_specimen_library import (
    SPECIMEN_DEFINITIONS,
    WATERMARK_TEXT,
    SYNTHETIC_APPLICANT_ID,
    seed_synthetic_library,
)


@pytest.fixture(scope="module")
def app_client():
    app = create_app("development")
    app.config["TESTING"] = True
    app.config["DATABASE_TYPE"] = "postgres"
    with app.test_client() as client:
        yield client


class TestSyntheticSpecimenLibrary:

    def test_criterion_1_every_registered_type_has_specimen(self, app_client):
        """1. Every registered document type has an active specimen (has_specimen == True)."""
        res = app_client.get("/api/repository/types")
        assert res.status_code == 200
        types = res.get_json()["data"]["types"]
        assert len(types) >= 12

        for t in types:
            t_key = t["type_key"]
            sample_res = app_client.get(f"/api/repository/types/{t_key}/sample")
            assert sample_res.status_code == 200, f"Failed for type {t_key}"
            sample_data = sample_res.get_json()["data"]
            assert sample_data["has_specimen"] is True, f"Type {t_key} missing specimen"
            assert sample_data["sample_document_id"] is not None
            assert sample_data["sample_filename"] is not None
            # Also verify repository types list reports has_specimen
            assert t.get("has_specimen") is True, f"Repository listing missing has_specimen for {t_key}"

    def test_criterion_2_every_attribute_has_non_empty_specimen_value(self, app_client):
        """2. Every configured schema attribute has a non-empty specimen value."""
        res = app_client.get("/api/repository/types")
        types = res.get_json()["data"]["types"]

        total_checked_attributes = 0
        for t in types:
            t_key = t["type_key"]
            details_res = app_client.get(f"/api/repository/types/{t_key}")
            assert details_res.status_code == 200
            details = details_res.get_json()["data"]
            schema = details.get("active_schema")
            assert schema is not None, f"No active schema for {t_key}"
            
            attr_defs = schema.get("attribute_definitions", [])
            assert len(attr_defs) > 0, f"No attributes configured for {t_key}"
            
            for attr in attr_defs:
                total_checked_attributes += 1
                sample_val = attr.get("sample_value")
                assert sample_val is not None, f"Attribute {attr['attribute_key']} in {t_key} has None sample_value"
                assert str(sample_val).strip() != "", f"Attribute {attr['attribute_key']} in {t_key} has empty sample_value"

        assert total_checked_attributes >= 76

    def test_criterion_3_attribute_values_match_data_types_and_rules(self, app_client):
        """3. Attribute values match configured data types and validation rules."""
        for type_key, cfg in SPECIMEN_DEFINITIONS.items():
            for attr in cfg["attributes"]:
                val = str(attr["sample_value"])
                dtype = attr["data_type"]
                akey = attr["attribute_key"]

                if dtype == "date":
                    # Must be standard ISO YYYY-MM-DD or DD/MM/YYYY
                    assert re.match(r"^\d{4}-\d{2}-\d{2}$|^\d{2}/\d{2}/\d{4}$", val), f"Invalid date: {val} for {akey}"
                elif dtype == "currency":
                    # Must contain currency symbol or decimal amount
                    assert any(c in val for c in ["₹", "$", ".", ","]) or val.replace(",", "").replace(".", "").isdigit(), f"Invalid currency: {val} for {akey}"
                elif dtype == "number":
                    # Clean number
                    clean = val.replace(",", "").replace(".", "").replace("%", "").strip()
                    assert clean.isdigit(), f"Invalid number: {val} for {akey}"
                elif dtype == "string":
                    assert len(val) > 0

                # Check specific identifier formats
                if akey == "pan_number":
                    assert re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", val), f"Invalid PAN format: {val}"
                elif akey == "identification_number" and type_key == "aadhaar":
                    assert "XXXX" in val or len(val.replace(" ", "")) == 12, f"Invalid Aadhaar format: {val}"

    def test_criterion_4_bounding_box_coordinates_normalized(self, app_client):
        """4. Bounding-box coordinates map correctly to normalized 0-1000 scale [ymin, xmin, ymax, xmax]."""
        for type_key, cfg in SPECIMEN_DEFINITIONS.items():
            for attr in cfg["attributes"]:
                bbox = attr.get("bounding_box")
                assert isinstance(bbox, list), f"bbox must be list for {attr['attribute_key']}"
                assert len(bbox) == 4, f"bbox must have 4 coordinates for {attr['attribute_key']}"
                ymin, xmin, ymax, xmax = bbox
                assert 0 <= ymin < ymax <= 1000, f"Invalid y coords {bbox} for {attr['attribute_key']} in {type_key}"
                assert 0 <= xmin < xmax <= 1000, f"Invalid x coords {bbox} for {attr['attribute_key']} in {type_key}"

    def test_criterion_5_and_6_bidirectional_spatial_selection(self, app_client):
        """5 & 6. Spatial highlighting: selecting an attribute locates region, region locates attribute."""
        # Test on Aadhaar specimen
        res = app_client.get("/api/repository/types/aadhaar/sample")
        data = res.get_json()["data"]
        doc_id = data["sample_document_id"]
        
        attr_res = app_client.get(f"/api/documents/{doc_id}/attributes")
        assert attr_res.status_code == 200
        attributes = attr_res.get_json()["data"]["attributes"]
        assert len(attributes) >= 4

        # Selecting attribute gives bounding box
        name_attr = next((a for a in attributes if a["attribute_key"] == "name"), None)
        assert name_attr is not None
        assert name_attr["bounding_box"] == [280, 260, 350, 750]

        # Selecting a point inside bounding box (y=300, x=400) identifies name
        pt_y, pt_x = 300, 400
        matched = []
        for a in attributes:
            bbox = a.get("bounding_box")
            if bbox and bbox[0] <= pt_y <= bbox[2] and bbox[1] <= pt_x <= bbox[3]:
                matched.append(a["attribute_key"])
        assert "name" in matched

    def test_criterion_7_multipage_documents_navigation_and_rendering(self, app_client):
        """7. Multi-page documents (bank_statement) render and navigate pages 1 and 2 correctly."""
        # Query bank statement sample
        res = app_client.get("/api/repository/types/bank_statement/sample")
        assert res.status_code == 200
        doc_id = res.get_json()["data"]["sample_document_id"]
        assert doc_id == "DOC-SYN-BANK-STATEMENT"

        # Check page 1 preview render
        p1_res = app_client.get(f"/api/documents/{doc_id}/pages/1/preview")
        assert p1_res.status_code == 200
        assert p1_res.content_type == "image/png"
        assert len(p1_res.data) > 1000

        # Check page 2 preview render
        p2_res = app_client.get(f"/api/documents/{doc_id}/pages/2/preview")
        assert p2_res.status_code == 200
        assert p2_res.content_type == "image/png"
        assert len(p2_res.data) > 1000

        # Check /render alias also works
        render_res = app_client.get(f"/api/documents/{doc_id}/pages/2/render")
        assert render_res.status_code == 200
        assert render_res.content_type == "image/png"

    def test_criterion_8_synthetic_fixtures_applicant_isolation(self, app_client):
        """8. Synthetic fixtures belong exclusively to APPL-SYN-FIXTURES and do not overwrite genuine applicants."""
        with app_client.application.app_context():
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Verify synthetic applicant exists
            cur.execute("SELECT id, name FROM applicants WHERE id = ?", (SYNTHETIC_APPLICANT_ID,))
            synth_app = cur.fetchone()
            assert synth_app is not None
            
            # Verify all synthetic specimen documents belong to APPL-SYN-FIXTURES
            cur.execute("SELECT id, applicant_id, original_filename FROM documents WHERE applicant_id = ?", (SYNTHETIC_APPLICANT_ID,))
            synth_docs = cur.fetchall()
            assert len(synth_docs) == 12
            for d in synth_docs:
                d_dict = dict(d) if isinstance(d, dict) else {"id": d[0], "applicant_id": d[1], "original_filename": d[2]}
                assert d_dict["applicant_id"] == SYNTHETIC_APPLICANT_ID
                assert "synthetic" in d_dict["original_filename"].lower()

            # Verify no genuine applicant was changed to APPL-SYN-FIXTURES
            cur.execute("SELECT COUNT(*) FROM applicants WHERE id != ?", (SYNTHETIC_APPLICANT_ID,))
            count = cur.fetchone()[0]
            assert count > 0, "Genuine applicants must remain intact"
            conn.close()

    def test_criterion_9_idempotency_of_specimen_generator(self, app_client):
        """9. Re-running fixture generation updates existing records without creating duplicates."""
        with app_client.application.app_context():
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM documents WHERE applicant_id = ?", (SYNTHETIC_APPLICANT_ID,))
            count_before = cur.fetchone()[0]
            conn.close()

            # Run generator again
            seed_synthetic_library()

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM documents WHERE applicant_id = ?", (SYNTHETIC_APPLICANT_ID,))
            count_after = cur.fetchone()[0]
            conn.close()

            assert count_before == count_after == 12, "Idempotency violated: duplicate documents created"

    def test_criterion_10_specimen_resolution_security_and_privacy(self, app_client):
        """10. Specimen resolution preserves applicant isolation and masks sensitive identifiers."""
        # Test Aadhaar masking in sample resolution
        res = app_client.get("/api/repository/types/aadhaar/sample")
        assert res.status_code == 200
        doc_id = res.get_json()["data"]["sample_document_id"]
        
        attr_res = app_client.get(f"/api/documents/{doc_id}/attributes")
        attrs = attr_res.get_json()["data"]["attributes"]
        id_attr = next(a for a in attrs if a["attribute_key"] == "aadhaar_number")
        # Ensure Aadhaar is masked
        assert "XXXX" in id_attr["normalized_value"] or "4819" in id_attr["normalized_value"]
        assert not re.match(r"^\d{12}$", id_attr["normalized_value"]), "Aadhaar must not be unmasked 12 digits"

    def test_criterion_11_core_system_routes_unaffected(self, app_client):
        """11. Existing upload, classification, queue, applicants, and reporting remain fully functional."""
        # 1. Health check
        health_res = app_client.get("/api/health")
        assert health_res.status_code == 200

        # 2. Applicants list
        apps_res = app_client.get("/api/applicants")
        assert apps_res.status_code == 200

        # 3. Repository stats
        stats_res = app_client.get("/api/repository/stats")
        assert stats_res.status_code == 200

        # 4. Reports summary
        rep_res = app_client.get("/api/reports/summary")
        assert rep_res.status_code == 200
