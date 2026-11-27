import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional

from backend.database.db import (
    create_processing_job,
    update_processing_job,
    get_processing_job,
    get_document,
    claim_specific_job,
    claim_next_queued_job,
    recover_stuck_jobs,
    list_pending_jobs,
)
from backend.services.webhook_dispatcher import WebhookDispatcher

logger = logging.getLogger(__name__)

# Global thread pool for asynchronous document processing jobs
_JOB_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="veridoc_job_worker")


class JobManager:
    """
    Coordinates asynchronous background job execution for document processing.
    Implements a strict finite state machine:
    queued -> processing (stages: intake -> extraction -> classification -> validation) -> completed / failed
    """

    @classmethod
    def submit_job(
        cls,
        document_id: str,
        processor: Any,
        db_path: Optional[str] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Create a queued processing job and dispatch background execution.
        Returns initial job record immediately.
        """
        job = create_processing_job(document_id=document_id, db_path=db_path)
        job_id = job["id"]

        _JOB_EXECUTOR.submit(
            cls._execute_job,
            job_id=job_id,
            document_id=document_id,
            processor=processor,
            db_path=db_path,
            max_retries=max_retries
        )

        return job

    @classmethod
    def process_synchronously(
        cls,
        document_id: str,
        processor: Any,
        db_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute the processing pipeline synchronously (e.g. when ?sync=true is requested).
        Registers and completes the job record in the database.
        """
        job = create_processing_job(document_id=document_id, db_path=db_path)
        job_id = job["id"]
        result = cls._execute_job(
            job_id=job_id,
            document_id=document_id,
            processor=processor,
            db_path=db_path,
            max_retries=1
        )
        return {
            "job": get_processing_job(job_id, db_path=db_path),
            "result": result
        }

    @classmethod
    def _execute_job(
        cls,
        job_id: str,
        document_id: str,
        processor: Any,
        db_path: Optional[str] = None,
        max_retries: int = 3
    ) -> Optional[Dict[str, Any]]:
        """Worker thread job execution logic with atomic claiming, state machine transitions, and exponential backoff retries."""
        # Atomic claim: prevent duplicate execution across workers or threads
        claimed = claim_specific_job(job_id=job_id, db_path=db_path)
        if not claimed:
            # Check if job was already claimed or completed
            job_state = get_processing_job(job_id, db_path=db_path)
            if not job_state or job_state.get("status") not in ("queued", "processing"):
                logger.info(f"Job {job_id} could not be claimed; already in status: {job_state.get('status') if job_state else 'unknown'}")
                return None

        attempt = 0
        last_error = None

        while attempt < max_retries:
            attempt += 1
            try:
                # 1. Transition: processing -> stage: extraction
                update_processing_job(
                    job_id=job_id,
                    status="processing",
                    progress=20,
                    stage="text_and_spatial_extraction",
                    db_path=db_path
                )

                # 2. Execute document pipeline (uses shared processor engine)
                result = processor.process_document_pipeline(document_id)

                # 3. Transition: processing -> stage: classification & attributes
                update_processing_job(
                    job_id=job_id,
                    progress=70,
                    stage="classification_and_attributes",
                    db_path=db_path
                )

                # 4. Success Completion
                doc_record = get_document(document_id, db_path=db_path)
                result_summary = {
                    "document_id": document_id,
                    "classified_type": result.get("classification", {}).get("classified_type", "unknown"),
                    "confidence": result.get("classification", {}).get("confidence", 0.0),
                    "attributes_count": len(result.get("extracted_fields", {}).get("attributes", [])),
                    "is_valid": result.get("validation", {}).get("is_valid", False),
                    "overall_status": result.get("validation", {}).get("overall_status", "unknown"),
                    "extraction_strategy": result.get("extraction_strategy", "unknown"),
                    "completed_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }

                update_processing_job(
                    job_id=job_id,
                    status="completed",
                    progress=100,
                    stage="completed",
                    result_summary=result_summary,
                    error_message=None,
                    db_path=db_path
                )

                # Dispatch Webhooks
                WebhookDispatcher.dispatch_event(
                    event_name="job.completed",
                    payload={"job_id": job_id, "document_id": document_id, "summary": result_summary},
                    db_path=db_path
                )
                WebhookDispatcher.dispatch_event(
                    event_name="document.classified",
                    payload={"document_id": document_id, "classified_type": result_summary["classified_type"]},
                    db_path=db_path
                )

                return result

            except Exception as exc:
                last_error = str(exc)
                logger.warning(f"Job {job_id} attempt {attempt}/{max_retries} failed: {exc}")
                if attempt < max_retries:
                    backoff_delay = 0.5 * (2 ** (attempt - 1))  # Exponential backoff: 0.5s, 1.0s, 2.0s...
                    time.sleep(backoff_delay)

        # All retries exhausted: mark job failed
        update_processing_job(
            job_id=job_id,
            status="failed",
            progress=100,
            stage="failed",
            error_message=f"Processing failed after {max_retries} attempts: {last_error}",
            db_path=db_path
        )

        WebhookDispatcher.dispatch_event(
            event_name="job.failed",
            payload={"job_id": job_id, "document_id": document_id, "error": last_error},
            db_path=db_path
        )
        return None

    @classmethod
    def recover_on_startup(
        cls,
        processor: Any,
        timeout_seconds: int = 300,
        db_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Recovers orphaned or interrupted jobs on backend startup.
        1. Identifies jobs stuck in 'processing' longer than timeout_seconds.
        2. Re-queues recoverable jobs (attempt_count < max_retries) or fails exhausted jobs.
        3. Dispatches any queued jobs to the background executor.
        """
        stats = recover_stuck_jobs(timeout_seconds=timeout_seconds, db_path=db_path)
        pending = list_pending_jobs(db_path=db_path)
        dispatched_count = 0
        for job in pending:
            if job.get("status") == "queued":
                doc_id = job.get("document_id")
                if doc_id:
                    _JOB_EXECUTOR.submit(
                        cls._execute_job,
                        job_id=job["id"],
                        document_id=doc_id,
                        processor=processor,
                        db_path=db_path,
                        max_retries=job.get("max_retries", 3)
                    )
                    dispatched_count += 1
        return {
            "recovered": stats.get("recovered", 0),
            "failed": stats.get("failed", 0),
            "dispatched_queued_jobs": dispatched_count
        }

    @classmethod
    def claim_and_process_next(
        cls,
        processor: Any,
        db_path: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Atomically claims and processes the next queued job.
        Useful for dedicated external polling workers or scheduled task runners.
        """
        claimed_job = claim_next_queued_job(db_path=db_path)
        if not claimed_job:
            return None
        return cls._execute_job(
            job_id=claimed_job["id"],
            document_id=claimed_job["document_id"],
            processor=processor,
            db_path=db_path,
            max_retries=claimed_job.get("max_retries", 3)
        )
        return None

    @classmethod
    def get_job_status(cls, job_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Fetch current status and progress of a processing job."""
        return get_processing_job(job_id, db_path=db_path)
