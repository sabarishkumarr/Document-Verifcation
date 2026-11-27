import io
import time
import json
import pytest
import pymupdf
from flask import Flask
from backend.app import create_app
from backend.database.db import (
    init_db,
    create_api_key,
    get_document,
    get_processing_job,
    create_webhook_subscription,
    list_webhook_subscriptions,
)
from backend.services.webhook_dispatcher import WebhookDispatcher


@pytest.fixture
def app(tmp_path):
    """Create Flask test application instance with temporary database."""
    test_db = str(tmp_path / "test_api_v1.db")
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


@pytest.fixture
def admin_key(app):
    """Create an admin API key for testing."""
    with app.app_context():
        db_path = app.config["DATABASE_PATH"]
        raw_key, record = create_api_key(
            name="Test Admin Key",
            permissions=["documents:read", "documents:write", "verification:review", "admin"],
            db_path=db_path
        )
        return raw_key


@pytest.fixture
def read_only_key(app):
    """Create a read-only API key."""
    with app.app_context():
        db_path = app.config["DATABASE_PATH"]
        raw_key, record = create_api_key(
            name="Test Read-Only Key",
            permissions=["documents:read"],
            db_path=db_path
        )
        return raw_key


def _make_sample_pdf(tmp_path, title="COMMERCIAL INVOICE", content="INV-2026-789 Total: 45000.00"):
    pdf_path = tmp_path / "sample_doc.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((50, 100), title)
    page.insert_text((50, 150), content)
    doc.save(str(pdf_path))
    doc.close()
    with open(pdf_path, "rb") as f:
        return f.read()


class TestHealthEndpoint:
    """Test public health endpoint."""

    def test_health_check(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "healthy"
        assert data["api_version"] == "v1"
        assert "database" in data
        assert "services" in data


class TestAuthenticationAndAuthorization:
    """Test API key authentication and RBAC scope authorization."""

    def test_missing_api_key(self, client):
        resp = client.get("/api/v1/document-types")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "UNAUTHORIZED"

    def test_invalid_api_key(self, client):
        headers = {"X-API-Key": "vdoc_live_invalid_key_1234567890"}
        resp = client.get("/api/v1/document-types", headers=headers)
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "INVALID_API_KEY"

    def test_insufficient_permissions(self, client, read_only_key):
        # Read-only key attempting to post a new document type (requires admin or documents:write)
        headers = {"X-API-Key": read_only_key}
        resp = client.post("/api/v1/document-types", headers=headers, json={
            "type_key": "custom_contract",
            "display_name": "Custom Contract"
        })
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["error"] == "FORBIDDEN"

    def test_valid_api_key_bearer_format(self, client, read_only_key):
        headers = {"Authorization": f"Bearer {read_only_key}"}
        resp = client.get("/api/v1/document-types", headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_api_key_management_flow(self, client, admin_key):
        headers = {"X-API-Key": admin_key}
        # 1. Create new key
        create_resp = client.post("/api/v1/auth/keys", headers=headers, json={
            "name": "Integration Partner Key",
            "permissions": ["documents:read", "documents:write"]
        })
        assert create_resp.status_code == 201
        key_data = create_resp.get_json()
        raw_new_key = key_data["api_key"]
        key_id = key_data["key_details"]["id"]
        assert raw_new_key.startswith("vdoc_live_")

        # 2. Use newly created key
        partner_headers = {"X-API-Key": raw_new_key}
        check_resp = client.get("/api/v1/document-types", headers=partner_headers)
        assert check_resp.status_code == 200

        # 3. List keys
        list_resp = client.get("/api/v1/auth/keys", headers=headers)
        assert list_resp.status_code == 200
        assert list_resp.get_json()["total"] >= 2

        # 4. Revoke key
        del_resp = client.delete(f"/api/v1/auth/keys/{key_id}", headers=headers)
        assert del_resp.status_code == 200

        # 5. Verify revoked key is rejected
        revoked_resp = client.get("/api/v1/document-types", headers=partner_headers)
        assert revoked_resp.status_code == 401


class TestDocumentIntakeAndAsyncProcessing:
    """Test document upload, asynchronous background execution, and polling."""

    def test_synchronous_upload_and_extraction(self, client, admin_key, tmp_path):
        pdf_bytes = _make_sample_pdf(tmp_path, "PAYSLIP FOR OCTOBER 2026", "Employee Name: RAHUL SHARMA Net Pay: 68500.00")
        headers = {"X-API-Key": admin_key}
        data = {
            "file": (io.BytesIO(pdf_bytes), "payslip.pdf")
        }
        resp = client.post("/api/v1/documents?sync=true", headers=headers, data=data, content_type="multipart/form-data")
        assert resp.status_code == 200
        res = resp.get_json()
        assert res["success"] is True
        assert res["mode"] == "synchronous"
        assert res["document_id"] is not None
        assert res["classification"]["classified_type"] == "salary_slip"
        assert len(res["attributes"]) >= 2

    def test_asynchronous_upload_and_polling(self, client, admin_key, tmp_path):
        pdf_bytes = _make_sample_pdf(tmp_path, "TAX INVOICE", "Invoice No: INV-2026-901 Total: 45000.00")
        headers = {"X-API-Key": admin_key}
        data = {
            "file": (io.BytesIO(pdf_bytes), "invoice.pdf")
        }
        # Default async upload returns 202 Accepted
        upload_resp = client.post("/api/v1/documents", headers=headers, data=data, content_type="multipart/form-data")
        assert upload_resp.status_code == 202
        upload_data = upload_resp.get_json()
        assert upload_data["success"] is True
        assert upload_data["mode"] == "asynchronous"
        job_id = upload_data["job_id"]
        doc_id = upload_data["document_id"]
        assert job_id.startswith("job_")

        # Poll job status
        max_attempts = 15
        job_completed = False
        final_job = None
        for _ in range(max_attempts):
            poll_resp = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
            assert poll_resp.status_code == 200
            final_job = poll_resp.get_json()
            if final_job["status"] == "completed":
                job_completed = True
                break
            time.sleep(0.3)

        assert job_completed is True, f"Job did not complete in time: {final_job}"
        assert final_job["progress"] == 100
        assert final_job["stage"] == "completed"
        assert final_job["result_summary"] is not None

        # Fetch full extraction result
        ext_resp = client.get(f"/api/v1/documents/{doc_id}/extraction", headers=headers)
        assert ext_resp.status_code == 200
        ext_data = ext_resp.get_json()
        assert ext_data["document_id"] == doc_id
        assert ext_data["classification"]["classified_type"] == "commercial_invoice"
        assert len(ext_data["attributes"]) >= 2


class TestReviewAndWorkflow:
    """Test human-in-the-loop compliance review endpoint."""

    def test_review_document(self, client, admin_key, tmp_path):
        # 1. Create a document synchronously
        pdf_bytes = _make_sample_pdf(tmp_path, "PASSPORT REPUBLIC OF INDIA", "Passport No: J4567890 Name: NEHA KAPOOR")
        headers = {"X-API-Key": admin_key}
        data = {"file": (io.BytesIO(pdf_bytes), "passport.pdf")}
        upload_resp = client.post("/api/v1/documents?sync=true", headers=headers, data=data, content_type="multipart/form-data")
        doc_id = upload_resp.get_json()["document_id"]

        # 2. Submit officer review
        review_payload = {
            "action": "approved",
            "notes": "All identity checks verified against MRZ line.",
            "officer_name": "Compliance Lead"
        }
        rev_resp = client.post(f"/api/v1/documents/{doc_id}/review", headers=headers, json=review_payload)
        assert rev_resp.status_code == 200
        rev_data = rev_resp.get_json()
        assert rev_data["success"] is True
        assert rev_data["review_status"] == "approved"

        # 3. Verify extraction endpoint reflects updated review status
        ext_resp = client.get(f"/api/v1/documents/{doc_id}/extraction", headers=headers)
        assert ext_resp.get_json()["review_status"] == "approved"


class TestDocumentTypesCatalogAPI:
    """Test document catalog retrieval and custom type registration."""

    def test_list_and_register_catalog_types(self, client, admin_key):
        headers = {"X-API-Key": admin_key}
        # List initial types
        list_resp = client.get("/api/v1/document-types", headers=headers)
        assert list_resp.status_code == 200
        types = list_resp.get_json()["document_types"]
        type_keys = [t["type_key"] for t in types]
        assert "pan" in type_keys
        assert "salary_slip" in type_keys

        # Register custom document type
        new_type = {
            "type_key": "tax_property_receipt",
            "display_name": "Property Tax Receipt",
            "category": "tax",
            "description": "Municipal corporation property tax payment receipt",
            "rules_json": {"keywords": [{"keyword": "PROPERTY TAX", "weight": 40}]}
        }
        create_resp = client.post("/api/v1/document-types", headers=headers, json=new_type)
        assert create_resp.status_code == 201
        created = create_resp.get_json()["document_type"]
        assert created["type_key"] == "tax_property_receipt"

        # Verify it appears in list
        updated_list = client.get("/api/v1/document-types", headers=headers).get_json()["document_types"]
        assert any(t["type_key"] == "tax_property_receipt" for t in updated_list)


class TestWebhooksManagementAPI:
    """Test webhook subscription management."""

    def test_webhook_crud(self, client, admin_key):
        headers = {"X-API-Key": admin_key}
        # 1. Create webhook
        sub_payload = {
            "target_url": "https://api.company.internal/webhooks/veridoc",
            "subscribed_events": ["job.completed", "document.reviewed"],
            "secret_token": "secret_test_token_12345"
        }
        create_resp = client.post("/api/v1/webhooks", headers=headers, json=sub_payload)
        assert create_resp.status_code == 201
        sub_data = create_resp.get_json()["webhook"]
        sub_id = sub_data["id"]
        assert sub_data["target_url"] == sub_payload["target_url"]

        # 2. List webhooks
        list_resp = client.get("/api/v1/webhooks", headers=headers)
        assert list_resp.status_code == 200
        assert list_resp.get_json()["total"] >= 1

        # 3. Delete webhook
        del_resp = client.delete(f"/api/v1/webhooks/{sub_id}", headers=headers)
        assert del_resp.status_code == 200
