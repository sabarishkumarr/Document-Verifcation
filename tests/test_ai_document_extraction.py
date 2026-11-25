import pytest
import json
from pathlib import Path
from backend.app import create_app
from backend.database.db import init_db
from backend.services.ai_extractor import AIDocumentExtractor
from backend.services.document_processor import DocumentProcessor


@pytest.fixture
def test_client(tmp_path):
    """Create test Flask app instance with isolated SQLite database and uploads folder."""
    test_db = tmp_path / "test_ai_veridoc.db"
    init_db(str(test_db))
    app = create_app("testing")
    app.config["DATABASE_PATH"] = str(test_db)
    app.config["UPLOAD_FOLDER"] = tmp_path / "uploads"
    app.config["PROCESSED_FOLDER"] = tmp_path / "processed"
    app.config["AI_EXTRACTION_ENABLED"] = True
    app.config["AI_PROVIDER"] = "mock"
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["PROCESSED_FOLDER"]).mkdir(parents=True, exist_ok=True)

    with app.test_client() as client:
        yield client, app


def test_ai_extractor_unconfigured_fallback():
    """Verify that AIDocumentExtractor gracefully reports unconfigured state and triggers fallback."""
    extractor = AIDocumentExtractor(provider="gemini", api_key="", enabled=True)
    assert not extractor.is_configured()
    status = extractor.get_status()
    assert not status["configured"]
    assert "not configured" in status["status_message"].lower()

    # Attempting extraction should request fallback cleanly without crashing
    res = extractor.extract_from_file("nonexistent_file.pdf")
    assert not res["success"]
    assert res["fallback_required"]


def test_ai_extractor_mock_multimodal_extraction(tmp_path):
    """Verify mock AI extraction returns standardized KYC schema with Aadhaar masking and source evidence."""
    mock_extractor = AIDocumentExtractor(provider="mock", enabled=True)
    assert mock_extractor.is_configured()

    # Create dummy synthetic PDF
    import pymupdf
    pdf_path = tmp_path / "neha_kapoor_passport.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "REPUBLIC OF INDIA PASSPORT\nPassport No: J4567890\nName: NEHA KAPOOR\nDOB: 14/11/1993")
    doc.save(str(pdf_path))
    doc.close()

    res = mock_extractor.extract_from_file(pdf_path, original_filename="neha_kapoor_passport.pdf")
    assert res["success"]
    assert not res["fallback_required"]
    fields = res["fields"]

    # Verify standardized output schema
    assert fields["document_type"] == "passport"
    assert fields["applicant_name"] == "NEHA KAPOOR"
    assert fields["date_of_birth"] == "1993-11-14"
    assert fields["gender"] == "FEMALE"
    assert fields["identification_number"] == "J4567890"
    assert fields["expiry_date"] == "2033-08-30"
    assert fields["extraction_method"] == "ai_mock"
    assert isinstance(fields["field_confidence"], dict)
    assert fields["field_confidence"]["applicant_name"] >= 0.70
    assert fields["source_evidence"]["page_number"] == 1
    assert "provider_metadata" in fields
    assert fields["provider_metadata"]["provider"] == "mock"

    # Verify backward-compatibility aliases
    assert fields["name"] == "NEHA KAPOOR"
    assert fields["dob"] == "1993-11-14"
    assert fields["id_number"] == "J4567890"


def test_ai_extractor_aadhaar_masking():
    """Verify that raw 12-digit Aadhaar numbers extracted by AI are strictly masked for privacy."""
    mock_extractor = AIDocumentExtractor(provider="mock", enabled=True)
    raw_ai_response = {
        "document_type": "aadhaar",
        "applicant_name": "Aarav Mehta",
        "identification_number": "1234 5678 9812",
        "date_of_birth": "1991-03-22",
        "gender": "MALE",
        "field_confidence": {"identification_number": 0.95, "applicant_name": 0.95}
    }
    normalized = mock_extractor._normalize_ai_response(raw_ai_response)
    assert normalized["identification_number"] == "XXXX-XXXX-9812"
    assert normalized["masked_id"] == "XXXX-XXXX-9812"
    assert normalized["id_number"] == "XXXX-XXXX-9812"


def test_api_ai_status_endpoint(test_client):
    """Verify GET /api/documents/ai-status returns valid service diagnostics."""
    client, app = test_client
    res = client.get("/api/documents/ai-status")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"]
    assert "provider" in data["data"]
    assert "configured" in data["data"]
    assert "status_message" in data["data"]


def test_hybrid_pipeline_ai_and_fallback(test_client, tmp_path):
    """Verify hybrid pipeline execution with mock AI provider and subsequent deterministic validation."""
    client, app = test_client

    # 1. Upload a synthetic test PDF
    import io
    import pymupdf
    pdf_bytes = io.BytesIO()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "PASSPORT REPUBLIC OF INDIA\nPassport No: J4567890\nName: NEHA KAPOOR\nDOB: 14/11/1993\nExpiry: 30/08/2033")
    doc.save(pdf_bytes)
    doc.close()
    pdf_bytes.seek(0)

    upload_res = client.post(
        "/api/documents/upload",
        data={
            "file": (pdf_bytes, "neha_kapoor_passport.pdf"),
            "applicant_id": "APPL-TEST-AI"
        },
        content_type="multipart/form-data"
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.get_json()["data"]["uploaded"][0]["id"]

    # 2. Process through pipeline
    proc_res = client.post(f"/api/documents/{doc_id}/process")
    assert proc_res.status_code == 200
    data = proc_res.get_json()["data"]["result"]

    assert data["extraction_strategy"] == "ai_multimodal"
    assert data["classification"]["classified_type"] == "passport"
    assert data["extracted_fields"]["applicant_name"] == "NEHA KAPOOR"
    assert data["extracted_fields"]["identification_number"] == "J4567890"

    # Deterministic validation must have executed
    assert data["validation"]["overall_status"] == "valid"
    assert data["validation"]["is_valid"] is True


def test_applicant_profile_editing_and_audit_history(test_client):
    """Verify updating applicant profile fields and inspecting review history ledger."""
    client, app = test_client

    # 1. Create applicant
    create_res = client.post("/api/applicants", json={
        "id": "APPL-EDIT-01",
        "name": "Original Name",
        "email": "orig@example.com"
    })
    assert create_res.status_code == 201

    # 2. Update applicant profile via PUT
    update_res = client.put("/api/applicants/APPL-EDIT-01", json={
        "name": "Updated Legal Name",
        "email": "updated@example.com",
        "phone": "+91 99999 88888",
        "risk_level": "medium",
        "notes": "Verified secondary residence proof"
    })
    assert update_res.status_code == 200
    app_data = update_res.get_json()["data"]["applicant"]
    assert app_data["name"] == "Updated Legal Name"
    assert app_data["email"] == "updated@example.com"
    assert app_data["phone"] == "+91 99999 88888"
    assert app_data["risk_level"] == "medium"
    assert app_data["notes"] == "Verified secondary residence proof"

    # 3. Retrieve profile and check audit history array
    get_res = client.get("/api/applicants/APPL-EDIT-01")
    assert get_res.status_code == 200
    prof_data = get_res.get_json()["data"]
    assert prof_data["applicant"]["name"] == "Updated Legal Name"
    assert "audit_history" in prof_data


def test_google_genai_sdk_client_initialization(monkeypatch):
    """Verify that AIDocumentExtractor configures the official Google GenAI SDK client."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-dummy-gemini-key-12345")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-1.5-flash")

    extractor = AIDocumentExtractor(provider="gemini")
    assert extractor.is_configured()
    assert extractor.model == "gemini-1.5-flash"
    assert extractor.genai_client is not None

    status = extractor.get_status()
    assert status["configured"] is True
    assert status["provider"] == "gemini"
    assert status["model"] == "gemini-1.5-flash"
    # Never expose the key in status or messages
    assert "test-dummy-gemini-key-12345" not in json.dumps(status)


def test_gemini_quota_exhausted_fallback_graceful(tmp_path, monkeypatch):
    """Verify that if Gemini encounters a quota limit or timeout, it triggers fallback without crashing."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-dummy-key")
    extractor = AIDocumentExtractor(provider="gemini")

    # Mock client generate_content to simulate a 429 quota exhaustion exception
    class MockErrorModels:
        def generate_content(self, *args, **kwargs):
            raise Exception("429 Resource has been exhausted (quota exceeded)")

    class MockClient:
        models = MockErrorModels()

    extractor.genai_client = MockClient()

    # Create dummy synthetic PDF
    import pymupdf
    pdf_path = tmp_path / "test_doc.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Sample Content")
    doc.save(str(pdf_path))
    doc.close()

    res = extractor.extract_from_file(pdf_path)
    assert not res["success"]
    assert res["fallback_required"] is True
    assert "429" in res["error"] or "exhausted" in res["error"].lower()


def test_all_five_kyc_categories_schema_compliance():
    """Verify strict schema normalization across all 5 document categories."""
    extractor = AIDocumentExtractor(provider="mock")

    sample_cases = [
        ("aadhaar", {"applicant_name": "Aarav Mehta", "identification_number": "9999 8888 7777", "date_of_birth": "1991-03-22", "gender": "MALE"}),
        ("pan", {"applicant_name": "Priya Sharma", "identification_number": "ABCPS1234F", "date_of_birth": "1990-07-15", "gender": "FEMALE"}),
        ("passport", {"applicant_name": "Neha Kapoor", "identification_number": "J4567890", "expiry_date": "2033-08-30", "gender": "FEMALE"}),
        ("voter_id", {"applicant_name": "Ananya Iyer", "identification_number": "WXY1234567", "gender": "FEMALE"}),
        ("driving_licence", {"applicant_name": "Rohan Nair", "identification_number": "DL-0120150078901", "expiry_date": "2024-01-01", "gender": "MALE"})
    ]

    for doc_type, raw_data in sample_cases:
        raw_data["document_type"] = doc_type
        norm = extractor._normalize_ai_response(raw_data)

        # Standard required fields present
        assert norm["document_type"] == doc_type
        assert "applicant_name" in norm
        assert "date_of_birth" in norm
        assert "gender" in norm
        assert "identification_number" in norm
        assert "address" in norm
        assert "issue_date" in norm
        assert "expiry_date" in norm
        assert "extraction_method" in norm
        assert "field_confidence" in norm
        assert "source_evidence" in norm
        assert "manual_review_required" in norm

        # Aadhaar must be masked
        if doc_type == "aadhaar":
            assert norm["identification_number"].startswith("XXXX-XXXX-")

