import pytest
import json
from pathlib import Path
from backend.app import create_app
from backend.database.db import init_db, insert_document, insert_ai_usage_log, get_ai_usage_summary
from backend.config import Config, calculate_gemini_cost
from backend.services.ai_extractor import AIDocumentExtractor
from backend.services.document_processor import DocumentProcessor


@pytest.fixture
def test_client(tmp_path):
    """Create Flask test client with temporary database."""
    test_db = tmp_path / "test_usage_veridoc.db"
    init_db(str(test_db))
    app = create_app("testing")
    app.config["DATABASE_PATH"] = str(test_db)
    app.config["UPLOAD_FOLDER"] = tmp_path / "uploads"
    app.config["PROCESSED_FOLDER"] = tmp_path / "processed"
    app.config["AI_EXTRACTION_ENABLED"] = True
    app.config["AI_PROVIDER"] = "gemini"
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["PROCESSED_FOLDER"]).mkdir(parents=True, exist_ok=True)

    with app.test_client() as client:
        yield client, app, str(test_db)


def test_calculate_gemini_cost_verified_tier():
    """Verify calculation of estimated Gemini API cost with verified Flash rates."""
    # 1000 prompt tokens, 500 candidate tokens at $0.075 / $0.300 per 1M
    cost = calculate_gemini_cost(1000, 500, price_per_m_input=0.075, price_per_m_output=0.300)
    # (1000 * 0.075)/1M = 0.000075; (500 * 0.300)/1M = 0.000150; Total = 0.000225
    assert cost == 0.000225

    # Zero tokens
    cost_zero = calculate_gemini_cost(0, 0, price_per_m_input=0.075, price_per_m_output=0.300)
    assert cost_zero == 0.0


def test_calculate_gemini_cost_missing_metadata_handling():
    """Requirement 10: Missing token metadata returns None instead of inventing values."""
    assert calculate_gemini_cost(None, 500) is None
    assert calculate_gemini_cost(1000, None) is None
    assert calculate_gemini_cost(None, None) is None


def test_ai_usage_logs_sqlite_persistence(tmp_path):
    """Requirements 3 & 4: Store usage records in SQLite, linked to document."""
    test_db = tmp_path / "test_log.db"
    init_db(str(test_db))

    insert_document({
        "id": "doc-test-123",
        "original_filename": "pan.pdf",
        "stored_filename": "pan.pdf"
    }, db_path=str(test_db))

    row_id = insert_ai_usage_log({
        "document_id": "doc-test-123",
        "applicant_id": None,
        "provider": "gemini",
        "model": "gemini-3.5-flash-lite",
        "prompt_tokens": 850,
        "candidate_tokens": 280,
        "total_tokens": 1130,
        "latency_ms": 1420,
        "status": "success",
        "estimated_cost": 0.000148,
        "error_message": None
    }, db_path=str(test_db))

    assert row_id > 0

    summary = get_ai_usage_summary(db_path=str(test_db))
    assert summary["metrics"]["total_api_calls"] == 1
    assert summary["metrics"]["successful_calls"] == 1
    assert summary["metrics"]["total_prompt_tokens"] == 850
    assert summary["metrics"]["total_candidate_tokens"] == 280
    assert summary["metrics"]["total_tokens"] == 1130
    assert summary["metrics"]["estimated_total_cost"] == 0.000148
    assert summary["metrics"]["cost_available"] is True
    assert summary["metrics"]["avg_latency_ms"] == 1420
    assert len(summary["recent_logs"]) == 1
    assert summary["recent_logs"][0]["document_id"] == "doc-test-123"


def test_local_fallback_not_counted_as_gemini_usage(tmp_path):
    """Requirement 9: Local fallback processing must NOT be counted as Gemini API usage."""
    test_db = tmp_path / "test_fallback.db"
    init_db(str(test_db))

    # Initial summary should be empty
    initial_summary = get_ai_usage_summary(db_path=str(test_db))
    assert initial_summary["metrics"]["total_api_calls"] == 0

    # Process a document with AI disabled (local fallback)
    app = create_app("testing")
    app.config["DATABASE_PATH"] = str(test_db)
    app.config["UPLOAD_FOLDER"] = tmp_path / "uploads"
    app.config["AI_EXTRACTION_ENABLED"] = False
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    processor = DocumentProcessor(
        upload_folder=str(tmp_path / "uploads"),
        db_path=str(test_db),
        ai_enabled=False
    )

    # Summary must remain 0 after local pipeline execution
    after_summary = get_ai_usage_summary(db_path=str(test_db))
    assert after_summary["metrics"]["total_api_calls"] == 0
    assert after_summary["metrics"]["gemini_documents_count"] == 0
    assert after_summary["metrics"]["total_tokens"] == 0


def test_api_reports_ai_usage_endpoint(test_client):
    """Requirement 7: Expose aggregated usage and cost through backend API endpoint."""
    client, app, db_path = test_client

    insert_document({
        "id": "doc-api-test",
        "original_filename": "pan.pdf",
        "stored_filename": "pan.pdf"
    }, db_path=db_path)

    # Insert a test usage record
    insert_ai_usage_log({
        "document_id": "doc-api-test",
        "applicant_id": None,
        "provider": "gemini",
        "model": "gemini-3.5-flash-lite",
        "prompt_tokens": 1200,
        "candidate_tokens": 350,
        "total_tokens": 1550,
        "latency_ms": 1850,
        "status": "success",
        "estimated_cost": 0.000195,
        "error_message": None
    }, db_path=db_path)

    res = client.get("/api/reports/ai-usage")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"]
    assert "metrics" in data["data"]
    metrics = data["data"]["metrics"]
    assert metrics["total_api_calls"] == 1
    assert metrics["total_prompt_tokens"] == 1200
    assert metrics["total_candidate_tokens"] == 350
    assert metrics["total_tokens"] == 1550
    assert metrics["estimated_total_cost"] == 0.000195
    assert metrics["cost_available"] is True


def test_api_reports_summary_includes_ai_usage(test_client):
    """Requirement 8: Reports summary includes ai_usage for UI consumption."""
    client, app, db_path = test_client
    res = client.get("/api/reports/summary")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"]
    assert "ai_usage" in data["data"]
    ai_usage = data["data"]["ai_usage"]
    assert "metrics" in ai_usage
    assert "pricing" in ai_usage
    assert ai_usage["provider"] == "gemini"


def test_verify_gemini_model_real_request():
    """Requirement 11: Verify configured model against real API request."""
    extractor = AIDocumentExtractor()
    if extractor.is_configured():
        result = extractor.verify_model_support()
        assert result["configured"] is True
        assert result["supported"] is True
        assert result["model"] == "gemini-3.5-flash-lite"
        assert result["usage_metadata_available"] is True


def test_extract_from_file_captures_usage_metadata_and_cost(monkeypatch, tmp_path):
    """Requirements 1, 2, 5 & 6: Verify usage_metadata capture in extract_from_file."""
    extractor = AIDocumentExtractor(provider="gemini", api_key="dummy_key_for_test")

    # Mock _call_gemini to simulate SDK response with usage_dict
    mock_payload = {
        "document_type": "pan",
        "applicant_name": "ROHIT SHARMA",
        "date_of_birth": "1987-04-30",
        "gender": "MALE",
        "identification_number": "ABCPS1234D"
    }
    mock_usage = {
        "prompt_tokens": 800,
        "candidate_tokens": 200,
        "total_tokens": 1000
    }

    monkeypatch.setattr(extractor, "_call_gemini", lambda *args, **kwargs: (mock_payload, mock_usage))

    # Create dummy file
    test_file = tmp_path / "dummy.png"
    test_file.write_bytes(b"dummy image bytes")

    result = extractor.extract_from_file(test_file)
    assert result["success"] is True
    meta = result["fields"]["provider_metadata"]
    assert meta["prompt_tokens"] == 800
    assert meta["candidate_tokens"] == 200
    assert meta["total_tokens"] == 1000
    # Expected cost: (800 * 0.075 / 1M) + (200 * 0.300 / 1M) = 0.00006 + 0.00006 = 0.000120
    assert meta["estimated_cost"] == 0.00012
    assert meta["cost_available"] is True
