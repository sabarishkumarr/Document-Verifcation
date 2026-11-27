"""
VeriDoc AI 2.0 — Visual Document Workspace & Interactive Marquee Test Suite

Tests:
1. Document page information endpoint (GET /api/documents/<id>/pages/info)
2. Document page high-DPI rendering (GET /api/documents/<id>/preview)
3. Normalized attributes retrieval with spatial bounding boxes (GET /api/documents/<id>/attributes)
4. Custom attribute creation and persistence (POST /api/documents/<id>/attributes)
5. Custom attribute deletion (DELETE /api/documents/<id>/attributes/<id>)
6. Interactive marquee region text extraction (POST /api/documents/<id>/marquee-extract)
"""

import io
import json
import pytest
import pymupdf
from pathlib import Path

from backend.app import create_app
from backend.database.db import (
    init_db,
    insert_document,
    get_document,
    get_document_extracted_attributes,
)


@pytest.fixture
def app(tmp_path):
    test_db = str(tmp_path / "test_workspace.db")
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


def _create_sample_pdf(file_path: Path) -> None:
    """Create a sample 2-page PDF document with spatial text."""
    doc = pymupdf.open()
    
    # Page 1
    p1 = doc.new_page(width=600, height=800)
    p1.insert_text((50, 100), "COMMERCIAL INVOICE", fontsize=16)
    p1.insert_text((50, 150), "Invoice Number: INV-2026-9901", fontsize=12)
    p1.insert_text((50, 200), "Total Gross Amount: USD 125,000.00", fontsize=12)
    p1.insert_text((50, 250), "Tax ID: US-EIN-992812", fontsize=12)

    # Page 2
    p2 = doc.new_page(width=600, height=800)
    p2.insert_text((50, 100), "Terms & Payment Instructions", fontsize=14)
    p2.insert_text((50, 150), "Swift BIC: CHASEUS33", fontsize=12)

    doc.save(str(file_path))
    doc.close()


@pytest.fixture
def seeded_doc(app):
    """Seed a test document with file on disk and database record."""
    with app.app_context():
        db_path = app.config["DATABASE_PATH"]
        uploads_dir = Path(app.config["UPLOAD_FOLDER"])
        uploads_dir.mkdir(parents=True, exist_ok=True)

        doc_id = "DOC-WORKSPACE-001"
        stored_filename = f"{doc_id}.pdf"
        file_path = uploads_dir / stored_filename
        _create_sample_pdf(file_path)

        metadata = {
            "page_count": 2,
            "spatial_tokens": [
                {"text": "Invoice", "bbox": [170, 80, 200, 150], "page": 1},
                {"text": "Number:", "bbox": [170, 155, 200, 230], "page": 1},
                {"text": "INV-2026-9901", "bbox": [170, 240, 200, 420], "page": 1},
                {"text": "Tax", "bbox": [290, 80, 320, 120], "page": 1},
                {"text": "ID:", "bbox": [290, 125, 320, 150], "page": 1},
                {"text": "US-EIN-992812", "bbox": [290, 155, 320, 310], "page": 1},
            ]
        }

        doc_data = {
            "id": doc_id,
            "original_filename": "commercial_invoice_9901.pdf",
            "stored_filename": stored_filename,
            "document_type": "commercial_invoice",
            "file_size": file_path.stat().st_size,
            "file_hash": "hash123",
            "mime_type": "application/pdf",
            "processing_status": "completed",
            "review_status": "pending",
        }

        insert_document(doc_data, db_path=db_path)

        from backend.database.db import get_db_connection
        conn = get_db_connection(db_path)
        cur = conn.cursor()
        cur.execute("""
            UPDATE documents
            SET extracted_fields = ?,
                extraction_metadata = ?
            WHERE id = ?;
        """, (
            json.dumps({
                "invoice_number": "INV-2026-9901",
                "total_amount": "USD 125,000.00",
                "tax_id": "US-EIN-992812"
            }),
            json.dumps(metadata),
            doc_id
        ))
        conn.commit()
        conn.close()

        return doc_id


class TestVisualDocumentWorkspaceAPI:
    """Verifies backend support for the visual document canvas and marquee extraction."""

    def test_pages_info_endpoint(self, client, seeded_doc):
        resp = client.get(f"/api/documents/{seeded_doc}/pages/info")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["document_id"] == seeded_doc
        assert data["page_count"] == 2
        assert len(data["pages"]) == 2
        assert data["pages"][0]["page_number"] == 1
        assert data["pages"][0]["width"] == 600
        assert data["pages"][0]["height"] == 800

    def test_preview_render_png_endpoint(self, client, seeded_doc):
        # Page 1 preview
        resp1 = client.get(f"/api/documents/{seeded_doc}/preview?page=1")
        assert resp1.status_code == 200
        assert resp1.mimetype == "image/png"
        assert len(resp1.data) > 1000

        # Page 2 preview via path parameter
        resp2 = client.get(f"/api/documents/{seeded_doc}/pages/2/render")
        assert resp2.status_code == 200
        assert resp2.mimetype == "image/png"

    def test_get_document_attributes_and_tokens(self, client, seeded_doc):
        resp = client.get(f"/api/documents/{seeded_doc}/attributes")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["document_id"] == seeded_doc
        assert "attributes" in data
        assert len(data["attributes"]) >= 3
        assert len(data["spatial_tokens"]) >= 6

    def test_add_and_delete_custom_attribute(self, client, seeded_doc):
        # 1. Add custom attribute
        attr_payload = {
            "attribute_key": "payment_swift_code",
            "attribute_label": "Payment SWIFT BIC",
            "attribute_value": "CHASEUS33",
            "data_type": "string",
            "page_number": 2,
            "bounding_box": [170, 80, 200, 350],
            "source_type": "custom"
        }
        create_res = client.post(f"/api/documents/{seeded_doc}/attributes", json=attr_payload)
        assert create_res.status_code == 201
        created_data = create_res.get_json()["data"]
        assert created_data["attribute_key"] == "payment_swift_code"
        assert created_data["raw_value"] == "CHASEUS33"
        attr_id = created_data["id"]

        # 2. Verify attribute is returned in attributes list
        list_res = client.get(f"/api/documents/{seeded_doc}/attributes")
        attrs = list_res.get_json()["data"]["attributes"]
        matching = [a for a in attrs if a["attribute_key"] == "payment_swift_code"]
        assert len(matching) == 1
        assert matching[0]["source_type"] == "custom"

        # 3. Delete custom attribute
        del_res = client.delete(f"/api/documents/{seeded_doc}/attributes/{attr_id}")
        assert del_res.status_code == 200

        # 4. Verify attribute is no longer active
        list_res2 = client.get(f"/api/documents/{seeded_doc}/attributes")
        attrs2 = list_res2.get_json()["data"]["attributes"]
        assert not any(a["id"] == attr_id for a in attrs2)

    def test_marquee_extract_text_region(self, client, seeded_doc):
        """
        User drags a marquee box over 'Invoice Number: INV-2026-9901' region.
        In our sample PDF (width 600, height 800):
        Text is at y=150 (approx 150/800 = 187/1000 normalized y).
        Bounding box: ymin=150, xmin=50, ymax=220, xmax=600.
        """
        payload = {
            "bbox": [150, 50, 230, 700],
            "page_number": 1
        }
        res = client.post(f"/api/documents/{seeded_doc}/marquee-extract", json=payload)
        assert res.status_code == 200
        data = res.get_json()["data"]
        assert data["document_id"] == seeded_doc
        assert data["page_number"] == 1
        assert "INV-2026-9901" in data["extracted_text"]

    def test_inspection_bounding_box_crash_regression(self, client, app, seeded_doc):
        """
        Regression test for Verification Queue Inspect blank-screen crash:
        Attributes with dict-format or string-format bounding boxes must be normalized
        to 4-element lists [ymin, xmin, ymax, xmax] so frontend map() and join() do not fail.
        """
        from backend.database.db import insert_extracted_attribute
        db_path = app.config["DATABASE_PATH"]

        # Insert attribute with dict-format bounding box (as seen in PostgreSQL jsonb)
        insert_extracted_attribute({
            "document_id": seeded_doc,
            "attribute_key": "dict_bbox_field",
            "attribute_label": "Dict BBox Field",
            "raw_value": "DICT_VAL",
            "normalized_value": "DICT_VAL",
            "data_type": "string",
            "confidence": 0.99,
            "source_type": "standard",
            "page_number": 1,
            "bounding_box": {"ymin": 307, "xmin": 290, "ymax": 335, "xmax": 572},
            "is_verified": True
        }, db_path=db_path)

        # Insert attribute with string-format bounding box
        insert_extracted_attribute({
            "document_id": seeded_doc,
            "attribute_key": "str_bbox_field",
            "attribute_label": "Str BBox Field",
            "raw_value": "STR_VAL",
            "normalized_value": "STR_VAL",
            "data_type": "string",
            "confidence": 0.99,
            "source_type": "standard",
            "page_number": 1,
            "bounding_box": "[400, 150, 450, 300]",
            "is_verified": True
        }, db_path=db_path)

        res = client.get(f"/api/documents/{seeded_doc}/attributes")
        assert res.status_code == 200
        attrs = res.get_json()["data"]["attributes"]

        dict_attr = next(a for a in attrs if a["attribute_key"] == "dict_bbox_field")
        assert isinstance(dict_attr["bounding_box"], list)
        assert dict_attr["bounding_box"] == [307, 290, 335, 572]

        str_attr = next(a for a in attrs if a["attribute_key"] == "str_bbox_field")
        assert isinstance(str_attr["bounding_box"], list)
        assert str_attr["bounding_box"] == [400, 150, 450, 300]
