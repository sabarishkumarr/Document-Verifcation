import pytest
import json
from pathlib import Path
from backend.app import create_app
from backend.database.db import get_dashboard_statistics, get_db_connection


@pytest.fixture
def client(tmp_path):
    test_db = tmp_path / "test_refinements.db"
    app = create_app("testing")
    app.config["DATABASE_PATH"] = str(test_db)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_demo_seed_and_idempotency(client):
    """Verify demo seed endpoint works and is idempotent."""
    res = client.post("/api/demo/seed")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["data"]["applicants_count"] == 10
    assert data["data"]["documents_count"] == 16

    # Run again without force: count should remain exactly 10 and 16
    res2 = client.post("/api/demo/seed")
    assert res2.status_code == 200
    
    app_res = client.get("/api/applicants")
    assert app_res.status_code == 200
    assert len(app_res.get_json()["data"]["applicants"]) == 10


def test_dashboard_reconciled_equation(client):
    """Verify that Total Documents = Approved + Pending + Issues."""
    client.post("/api/demo/seed")

    res = client.get("/api/dashboard/stats")
    assert res.status_code == 200
    stats = res.get_json()["data"]

    total = stats["total_documents"]
    approved = stats["approved_count"]
    pending = stats["pending_review_count"]
    issues = stats["issues_count"]

    assert total == approved + pending + issues
    assert total == 16


def test_global_search_endpoints(client):
    """Verify global search finds both applicants and documents."""
    client.post("/api/demo/seed")

    # Search for Priya
    res1 = client.get("/api/search?q=Priya")
    assert res1.status_code == 200
    data1 = res1.get_json()["data"]
    assert len(data1["applicants"]) >= 1
    assert data1["applicants"][0]["name"] == "Priya Sharma"
    assert len(data1["documents"]) >= 1

    # Search for PAN ID number ABCPS1234F
    res2 = client.get("/api/search?q=ABCPS1234F")
    assert res2.status_code == 200
    data2 = res2.get_json()["data"]
    assert len(data2["documents"]) >= 1
    assert data2["documents"][0]["original_filename"] == "demo_priya_sharma_pan.pdf"

    # Search empty
    res3 = client.get("/api/search?q=")
    assert res3.status_code == 200
    assert res3.get_json()["data"]["applicants"] == []
    assert res3.get_json()["data"]["documents"] == []


def test_custom_officer_review_audit(client):
    """Verify that custom officer name is audited upon review submission."""
    client.post("/api/demo/seed")

    custom_officer = "Sneha Patel (Senior KYC Specialist)"
    review_payload = {
        "decision": "approved",
        "officer_name": custom_officer,
        "notes": "Verified against physical file copy."
    }

    res = client.post("/api/documents/DOC-DEMO-013/review", json=review_payload)
    assert res.status_code == 200
    review_data = res.get_json()["data"]["review"]
    assert review_data["reviewed_by"] == custom_officer
    assert review_data["review_status"] == "approved"


def test_reports_summary_and_downloads(client):
    """Verify that reports summary, CSV download, and JSON download work properly."""
    client.post("/api/demo/seed")

    # 1. Summary API
    sum_res = client.get("/api/reports/summary")
    assert sum_res.status_code == 200
    sum_data = sum_res.get_json()["data"]
    assert sum_data["total_applicants"] == 10
    assert sum_data["total_documents"] == 16
    assert len(sum_data["applicants"]) == 10

    # 2. CSV Download
    csv_res = client.get("/api/reports/download?format=csv")
    assert csv_res.status_code == 200
    assert csv_res.mimetype == "text/csv"
    assert "attachment; filename=veridoc_kyc_verification_report.csv" in csv_res.headers.get("Content-Disposition")
    csv_text = csv_res.data.decode("utf-8")
    assert "Applicant ID,Applicant Name,Verification Status" in csv_text
    assert "Priya Sharma" in csv_text

    # 3. JSON Download
    json_res = client.get("/api/reports/download?format=json")
    assert json_res.status_code == 200
    assert json_res.mimetype == "application/json"
    assert "attachment; filename=veridoc_kyc_verification_report.json" in json_res.headers.get("Content-Disposition")
    json_data = json.loads(json_res.data)
    assert json_data["total_applicants"] == 10


def test_resubmission_requested_and_field_edits(client):
    """Verify resubmission_requested decision and saving edited fields."""
    client.post("/api/demo/seed")

    payload = {
        "decision": "resubmission_requested",
        "officer_name": "Review Officer",
        "notes": "Document partially blurry, please upload higher resolution copy.",
        "edited_fields": {
            "name": "Priya Sharma",
            "dob": "1992-05-14"
        }
    }

    res = client.post("/api/documents/DOC-DEMO-001/review", json=payload)
    assert res.status_code == 200
    data = res.get_json()["data"]["review"]
    assert data["review_status"] == "resubmission_requested"
    assert data["extracted_fields"]["name"] == "Priya Sharma"

    # Check applicant status is updated to requires_attention
    app_res = client.get("/api/applicants/APP-DEMO-001")
    assert app_res.status_code == 200
    assert app_res.get_json()["data"]["applicant"]["status"] == "requires_attention"

