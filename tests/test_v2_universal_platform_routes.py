import pytest
import json
from backend.app import create_app
from backend.database.db import (
    get_db_connection,
    init_db,
    insert_applicant,
    insert_document,
    get_applicant_triangulation,
    save_applicant_triangulation,
    list_benchmark_runs
)

@pytest.fixture
def client(tmp_path):
    test_db = str(tmp_path / "test_platform_v2.db")
    init_db(db_path=test_db)
    app = create_app("testing")
    app.config["DATABASE_PATH"] = test_db
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client, test_db


def test_repository_stats_and_types_api(client):
    test_client, db_path = client
    
    # Test GET /api/repository/stats
    res = test_client.get("/api/repository/stats")
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert "total_types" in data
    assert "active_types" in data
    assert "system_types" in data

    # Test GET /api/repository/types
    res = test_client.get("/api/repository/types")
    assert res.status_code == 200
    types = res.get_json()["data"]["types"]
    assert len(types) >= 10
    
    # Test POST /api/repository/types
    payload = {
        "type_key": "gst_registration_cert",
        "display_name": "GST Registration Certificate",
        "category": "tax",
        "description": "Goods and Services Tax certificate issued by CBIC",
        "source_origin": "employee_created",
        "attributes": [
            {
                "attribute_key": "gstin",
                "display_label": "GSTIN Number",
                "data_type": "string",
                "required": True,
                "confidence_threshold": 0.85
            }
        ]
    }
    res = test_client.post("/api/repository/types", json=payload)
    assert res.status_code == 201
    created = res.get_json()["data"]
    assert created["type_key"] == "gst_registration_cert"
    assert created["active_schema"]["version"] == 1


def test_applicant_triangulation_api(client):
    test_client, db_path = client

    # Seed applicant
    insert_applicant(
        "APP-TEST-TRI-01",
        name="Rajesh Sharma",
        email="rajesh@example.com",
        phone="9876543210",
        db_path=db_path
    )

    # Seed 2 documents
    insert_document({
        "id": "DOC-PAN-01",
        "applicant_id": "APP-TEST-TRI-01",
        "original_filename": "pan.pdf",
        "document_type": "pan",
        "extracted_fields": json.dumps({"name": "Rajesh Sharma", "dob": "1985-05-12", "id_number": "ABCDE1234F"}),
        "processing_status": "completed"
    }, db_path=db_path)

    insert_document({
        "id": "DOC-AADHAAR-01",
        "applicant_id": "APP-TEST-TRI-01",
        "original_filename": "aadhaar.pdf",
        "document_type": "aadhaar",
        "extracted_fields": json.dumps({"name": "Rajesh Sharma", "dob": "1985-05-12", "id_number": "XXXX-XXXX-9999"}),
        "processing_status": "completed"
    }, db_path=db_path)

    # Test GET /api/applicants/APP-TEST-TRI-01/triangulation
    res = test_client.get("/api/applicants/APP-TEST-TRI-01/triangulation")
    assert res.status_code == 200
    tri = res.get_json()["data"]["triangulation"]
    assert tri["applicant_id"] == "APP-TEST-TRI-01"
    assert "triangulation_matrix" in tri
    assert tri["overall_status"] in ("VERIFIED", "FLAGGED", "NEEDS_REVIEW")

    # Test POST /api/applicants/APP-TEST-TRI-01/triangulation (force recompute & save)
    res = test_client.post("/api/applicants/APP-TEST-TRI-01/triangulation", json={"verified_by": "Test Officer"})
    assert res.status_code == 200
    saved = res.get_json()["data"]["triangulation"]
    assert saved["applicant_id"] == "APP-TEST-TRI-01"

    # Test POST /api/applicants/APP-TEST-TRI-01/triangulation/resolve
    res = test_client.post("/api/applicants/APP-TEST-TRI-01/triangulation/resolve", json={
        "overall_status": "MANUAL_RESOLVED",
        "notes": "Verified against physical card."
    })
    assert res.status_code == 200
    resolved = res.get_json()["data"]["triangulation"]
    assert resolved["overall_status"] == "MANUAL_RESOLVED"


def test_evaluation_benchmark_api(client):
    test_client, db_path = client

    # Test GET /api/evaluation/runs (empty initially)
    res = test_client.get("/api/evaluation/runs")
    assert res.status_code == 200
    assert "runs" in res.get_json()["data"]

    # Test POST /api/evaluation/benchmark
    res = test_client.post("/api/evaluation/benchmark", json={
        "dataset_name": "synthetic_kyc_10",
        "executed_by": "Test Suite Runner"
    })
    assert res.status_code == 200
    data = res.get_json()["data"]
    run = data["run"]
    assert run["accuracy"] >= 0.8
    assert run["precision_score"] >= 0.8
    assert run["total_documents"] == 25
    assert run["status"] == "completed"

    # Verify run recorded in history
    res = test_client.get("/api/evaluation/runs")
    assert res.status_code == 200
    runs = res.get_json()["data"]["runs"]
    assert len(runs) >= 1
