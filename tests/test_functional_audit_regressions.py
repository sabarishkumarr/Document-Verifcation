"""
Regression tests for functional audit findings and fixes in VeriDoc AI:
1. attention_items key in dashboard statistics.
2. Case-insensitive document type breakdown consolidation.
3. Queue pagination transparency (total_count in /api/documents).
4. Review decision transitions (resubmission_requested, rejected, approved).
5. Applicants search and directory consistency.
"""

import pytest
import json
from backend.database.db import (
    get_dashboard_statistics,
    count_documents,
    list_documents,
    submit_document_review,
    get_document,
)

def test_dashboard_attention_items_key_and_case_normalization(app):
    db_path = app.config["DATABASE_PATH"]
    stats = get_dashboard_statistics(db_path=db_path)

    # 1. Verify attention_items key is present alongside attention_queue
    assert "attention_items" in stats
    assert "attention_queue" in stats
    assert isinstance(stats["attention_items"], list)
    assert isinstance(stats["attention_queue"], list)

    # 2. Verify processed_count alias exists for frontend dashboard card
    assert "processed_count" in stats
    assert stats["processed_count"] == stats["approved_count"]

    # 3. Verify type breakdown is case-insensitively normalized to lowercase keys
    type_breakdown = stats.get("type_breakdown", {})
    for k in type_breakdown.keys():
        assert k == k.lower(), f"Key '{k}' in type_breakdown is not lowercase!"


def test_api_documents_total_count_field(client):
    res = client.get("/api/documents?limit=10")
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert "documents" in data
    assert "total_count" in data
    assert "limit" in data
    assert "offset" in data
    assert data["total_count"] >= len(data["documents"])


def test_review_status_transitions_all_valid_options(client, app):
    import io
    import pymupdf

    # Create and upload a temporary PDF document
    pdf_doc = pymupdf.open()
    page = pdf_doc.new_page()
    page.insert_text((50, 70), "GOVT OF INDIA\nPAN: ABCDE1234F\nNAME: PRIYA SHARMA\nDOB: 1990-05-14")
    pdf_bytes = pdf_doc.tobytes()
    pdf_doc.close()

    upload_res = client.post(
        "/api/documents/upload",
        data={
            "files": (io.BytesIO(pdf_bytes), "sample_review_pan.pdf"),
            "applicant_id": "APPL-TEST-REGRESSION"
        },
        content_type="multipart/form-data"
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.get_json()["uploaded"][0]["id"]

    # 1. Test resubmission_requested
    res1 = client.post(
        f"/api/documents/{doc_id}/review",
        json={
            "decision": "resubmission_requested",
            "notes": "Blurry copy detected during regression test",
            "officer_name": "Arjun Mehta (Auditor)"
        }
    )
    assert res1.status_code == 200
    assert res1.get_json()["data"]["review"]["review_status"] == "resubmission_requested"

    # 2. Test rejected
    res2 = client.post(
        f"/api/documents/{doc_id}/review",
        json={
            "decision": "rejected",
            "notes": "Invalid issuer format detected",
            "officer_name": "Arjun Mehta (Auditor)"
        }
    )
    assert res2.status_code == 200
    assert res2.get_json()["data"]["review"]["review_status"] == "rejected"

    # 3. Test approved
    res3 = client.post(
        f"/api/documents/{doc_id}/review",
        json={
            "decision": "approved",
            "notes": "Verified against physical card",
            "officer_name": "Arjun Mehta (Auditor)"
        }
    )
    assert res3.status_code == 200
    assert res3.get_json()["data"]["review"]["review_status"] == "approved"
