"""
VeriDoc AI 2.0 — Asynchronous Worker & Job Reliability Audit Test Suite

Validates:
1. Job persistence and recovery after backend restart / interruption.
2. Atomic job claiming and duplicate processing prevention.
3. Recovery of jobs stuck in processing state (re-queue vs failure upon retry limit).
4. Worker retry limits, exponential backoff, and terminal failure handling.
5. Outbound webhook delivery retries, failure handling, and HMAC-SHA256 signature verification.
6. API key lifecycle: creation, scope authorization enforcement, and immediate revocation.
"""

import time
import json
import pytest
from unittest.mock import patch, MagicMock
from flask import Flask

from backend.app import create_app
from backend.database.db import (
    init_db,
    get_db_connection,
    insert_document,
    create_api_key,
    revoke_api_key,
    validate_api_key,
    create_processing_job,
    update_processing_job,
    get_processing_job,
    claim_specific_job,
    claim_next_queued_job,
    recover_stuck_jobs,
    list_pending_jobs,
    create_webhook_subscription,
    list_webhook_subscriptions,
)
from backend.services.async_worker import JobManager
from backend.services.webhook_dispatcher import WebhookDispatcher


def _seed_doc(doc_id: str, db_path: str):
    """Seed a document record to satisfy processing_jobs foreign key constraint."""
    insert_document({
        "id": doc_id,
        "original_filename": f"{doc_id}.pdf",
        "stored_filename": f"{doc_id}.pdf",
        "document_type": "commercial_invoice",
        "file_size": 1024,
        "file_hash": "dummyhash",
        "mime_type": "application/pdf",
        "processing_status": "pending",
        "review_status": "pending"
    }, db_path=db_path)


@pytest.fixture
def app(tmp_path):
    """Create Flask test application instance with isolated temporary database."""
    test_db = str(tmp_path / "test_reliability.db")
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


class TestWorkerReliabilityAndAtomicClaiming:
    """Verifies atomic claiming, duplicate prevention, and restart recovery."""

    def test_atomic_job_claiming_prevents_duplicate_workers(self, app):
        """
        When two concurrent workers or threads attempt to claim the same queued job,
        exactly ONE worker must succeed, and the second must be rejected (return False).
        """
        with app.app_context():
            db_path = app.config["DATABASE_PATH"]
            _seed_doc("DOC-TEST-ATOMIC-001", db_path)
            job = create_processing_job("DOC-TEST-ATOMIC-001", db_path=db_path)
            job_id = job["id"]

            # First worker claims the job
            claimed_worker1 = claim_specific_job(job_id, db_path=db_path)
            assert claimed_worker1 is True, "Worker 1 must successfully claim queued job"

            # Second worker attempts to claim the exact same job
            claimed_worker2 = claim_specific_job(job_id, db_path=db_path)
            assert claimed_worker2 is False, "Worker 2 must be rejected; duplicate claiming prevented"

            # Verify state
            persisted = get_processing_job(job_id, db_path=db_path)
            assert persisted["status"] == "processing"
            assert persisted["attempt_count"] == 1

    def test_claim_next_queued_job_order(self, app):
        """claim_next_queued_job claims jobs in strict FIFO order."""
        with app.app_context():
            db_path = app.config["DATABASE_PATH"]
            _seed_doc("DOC-FIFO-001", db_path)
            _seed_doc("DOC-FIFO-002", db_path)
            job1 = create_processing_job("DOC-FIFO-001", db_path=db_path)
            time.sleep(0.01)
            job2 = create_processing_job("DOC-FIFO-002", db_path=db_path)

            claimed1 = claim_next_queued_job(db_path=db_path)
            assert claimed1 is not None
            assert claimed1["id"] == job1["id"]

            claimed2 = claim_next_queued_job(db_path=db_path)
            assert claimed2 is not None
            assert claimed2["id"] == job2["id"]

            # Queue empty now
            claimed3 = claim_next_queued_job(db_path=db_path)
            assert claimed3 is None

    def test_stuck_job_recovery_requeues_and_fails_on_exhaustion(self, app):
        """
        Jobs stuck in 'processing' beyond timeout are recovered to 'queued'
        if attempt_count < max_retries, and marked 'failed' if attempt_count >= max_retries.
        """
        with app.app_context():
            db_path = app.config["DATABASE_PATH"]
            _seed_doc("DOC-STUCK-A", db_path)
            _seed_doc("DOC-STUCK-B", db_path)

            job_a = create_processing_job("DOC-STUCK-A", db_path=db_path)
            job_b = create_processing_job("DOC-STUCK-B", db_path=db_path)

            # Update their states to simulated past stuck processing times
            conn = get_db_connection(db_path)
            cur = conn.cursor()
            cur.execute("""
                UPDATE processing_jobs
                SET status = 'processing',
                    started_at = datetime('now', '-600 seconds'),
                    attempt_count = 1,
                    max_retries = 3
                WHERE id = ?;
            """, (job_a["id"],))

            cur.execute("""
                UPDATE processing_jobs
                SET status = 'processing',
                    started_at = datetime('now', '-600 seconds'),
                    attempt_count = 3,
                    max_retries = 3
                WHERE id = ?;
            """, (job_b["id"],))
            conn.commit()
            conn.close()

            # Execute recovery with 300-second timeout threshold
            stats = recover_stuck_jobs(timeout_seconds=300, db_path=db_path)
            assert stats["recovered"] == 1
            assert stats["failed"] == 1

            # Verify Job A became queued
            recovered_a = get_processing_job(job_a["id"], db_path=db_path)
            assert recovered_a["status"] == "queued"
            assert recovered_a["stage"] == "recovered_requeued"

            # Verify Job B became failed
            recovered_b = get_processing_job(job_b["id"], db_path=db_path)
            assert recovered_b["status"] == "failed"
            assert recovered_b["stage"] == "failed"
            assert "exceeded maximum retries" in recovered_b["error_message"]

    def test_backend_restart_recovery_workflow(self, app):
        """JobManager.recover_on_startup recovers stuck jobs and dispatches pending queued jobs."""
        with app.app_context():
            db_path = app.config["DATABASE_PATH"]
            _seed_doc("DOC-RESTART-001", db_path)

            # Seed an interrupted job from previous server crash
            stuck_job = create_processing_job("DOC-RESTART-001", db_path=db_path)
            conn = get_db_connection(db_path)
            cur = conn.cursor()
            cur.execute("""
                UPDATE processing_jobs
                SET status = 'processing',
                    started_at = datetime('now', '-400 seconds'),
                    attempt_count = 1
                WHERE id = ?;
            """, (stuck_job["id"],))
            conn.commit()
            conn.close()

            # Mock document processor
            mock_processor = MagicMock()
            mock_processor.process_document_pipeline.return_value = {
                "classification": {"classified_type": "invoice", "confidence": 0.95},
                "extracted_fields": {"attributes": [{"key": "invoice_number", "value": "INV-100"}]},
                "validation": {"is_valid": True, "overall_status": "valid"},
                "extraction_strategy": "mock"
            }

            # Run startup recovery
            recovery_report = JobManager.recover_on_startup(
                processor=mock_processor,
                timeout_seconds=300,
                db_path=db_path
            )

            assert recovery_report["recovered"] == 1
            assert recovery_report["dispatched_queued_jobs"] >= 1

            # Give worker thread a moment to process the dispatched job
            time.sleep(0.5)

            final_job = get_processing_job(stuck_job["id"], db_path=db_path)
            assert final_job["status"] == "completed"
            assert final_job["progress"] == 100


class TestRetryLimitsAndFailureHandling:
    """Verifies retry limits, exponential backoff, and terminal failure handling."""

    def test_worker_retries_and_terminal_failure(self, app):
        """When the processing pipeline consistently raises an exception, the job retries up to max_retries and transitions to failed."""
        with app.app_context():
            db_path = app.config["DATABASE_PATH"]
            _seed_doc("DOC-FAILING-001", db_path)
            job = create_processing_job("DOC-FAILING-001", db_path=db_path)
            job_id = job["id"]

            failing_processor = MagicMock()
            failing_processor.process_document_pipeline.side_effect = RuntimeError("OCR engine crashed")

            with patch("time.sleep") as mock_sleep:
                result = JobManager._execute_job(
                    job_id=job_id,
                    document_id="DOC-FAILING-001",
                    processor=failing_processor,
                    db_path=db_path,
                    max_retries=3
                )

            assert result is None, "Failed job returns None"
            assert failing_processor.process_document_pipeline.call_count == 3
            # Check backoff sleep was called twice (between attempt 1->2 and 2->3)
            assert mock_sleep.call_count == 2

            persisted = get_processing_job(job_id, db_path=db_path)
            assert persisted["status"] == "failed"
            assert persisted["stage"] == "failed"
            assert persisted["progress"] == 100
            assert "OCR engine crashed" in persisted["error_message"]
            assert "failed after 3 attempts" in persisted["error_message"]


class TestWebhookReliabilityAndSignatures:
    """Verifies HMAC-SHA256 signatures, tampered payload rejection, and delivery retries."""

    def test_hmac_sha256_signature_generation_and_verification(self):
        secret = "secret_key_1234567890abcdef"
        payload = b'{"event":"job.completed","data":{"job_id":"JOB-123"}}'

        # Compute valid signature
        sig_hex = WebhookDispatcher.compute_signature(secret, payload)
        sig_header = f"sha256={sig_hex}"

        # 1. Valid signature passes
        assert WebhookDispatcher.verify_signature(secret, payload, sig_header) is True

        # 2. Tampered payload fails
        tampered_payload = b'{"event":"job.completed","data":{"job_id":"JOB-999"}}'
        assert WebhookDispatcher.verify_signature(secret, tampered_payload, sig_header) is False

        # 3. Wrong secret fails
        assert WebhookDispatcher.verify_signature("wrong_secret", payload, sig_header) is False

        # 4. Malformed header fails
        assert WebhookDispatcher.verify_signature(secret, payload, "invalid_header") is False
        assert WebhookDispatcher.verify_signature(secret, payload, f"sha512={sig_hex}") is False

    def test_webhook_delivery_retries_on_failure(self):
        """Webhook delivery retries up to max_retries when endpoint returns errors."""
        with patch.object(WebhookDispatcher, "_deliver_webhook") as mock_deliver:
            # Simulate first two attempts failing, third succeeding
            mock_deliver.side_effect = [False, False, True]

            with patch("time.sleep") as mock_sleep:
                delivered = WebhookDispatcher._deliver_with_retries(
                    target_url="https://api.partner.com/webhook",
                    secret_token="sub_secret_token",
                    event_name="job.completed",
                    body_bytes=b'{"test":1}',
                    max_retries=3
                )

            assert delivered is True
            assert mock_deliver.call_count == 3
            assert mock_sleep.call_count == 2

    def test_webhook_delivery_exhaustion(self):
        """Webhook delivery returns False after exhausting all retries."""
        with patch.object(WebhookDispatcher, "_deliver_webhook") as mock_deliver:
            mock_deliver.return_value = False

            with patch("time.sleep"):
                delivered = WebhookDispatcher._deliver_with_retries(
                    target_url="https://api.partner.com/webhook",
                    secret_token="sub_secret_token",
                    event_name="job.completed",
                    body_bytes=b'{"test":1}',
                    max_retries=3
                )

            assert delivered is False
            assert mock_deliver.call_count == 3


class TestApiKeyRevocationAndScopeEnforcement:
    """Verifies API key creation, scope restrictions, and immediate revocation enforcement."""

    def test_scoped_permissions_enforcement(self, client, app):
        with app.app_context():
            db_path = app.config["DATABASE_PATH"]
            # Create a read-only key (only documents:read)
            read_key, _ = create_api_key(
                name="Read-Only Client",
                permissions=["documents:read"],
                db_path=db_path
            )

        headers = {"X-API-Key": read_key}

        # 1. Can access GET document-types (requires documents:read)
        get_res = client.get("/api/v1/document-types", headers=headers)
        assert get_res.status_code == 200

        # 2. Cannot access POST document-types (requires admin)
        post_type_res = client.post("/api/v1/document-types", json={"type_key": "tax_cert"}, headers=headers)
        assert post_type_res.status_code == 403
        data = post_type_res.get_json()
        assert data["error"] == "FORBIDDEN"
        assert "lacks required scope" in data["message"]

        # 3. Cannot upload document (requires documents:write)
        upload_res = client.post(
            "/api/v1/documents",
            data={"file": (None, "test.pdf")},
            content_type="multipart/form-data",
            headers=headers
        )
        assert upload_res.status_code == 403

    def test_immediate_api_key_revocation(self, client, app):
        with app.app_context():
            db_path = app.config["DATABASE_PATH"]
            raw_key, record = create_api_key(
                name="Key To Revoke",
                permissions=["documents:read", "documents:write"],
                db_path=db_path
            )
            key_id = record["id"]

        headers = {"X-API-Key": raw_key}

        # Key is active: works
        res = client.get("/api/v1/document-types", headers=headers)
        assert res.status_code == 200

        # Revoke key
        with app.app_context():
            revoked = revoke_api_key(key_id, db_path=db_path)
            assert revoked is True

        # Revoked key immediately receives 401 UNAUTHORIZED
        revoked_res = client.get("/api/v1/document-types", headers=headers)
        assert revoked_res.status_code == 401
        data = revoked_res.get_json()
        assert data["error"] == "INVALID_API_KEY"
        assert "revoked" in data["message"]
