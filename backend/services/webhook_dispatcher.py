import json
import hmac
import hashlib
import time
import logging
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Dedicated thread pool for async webhook delivery
_WEBHOOK_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="veridoc_webhook")


class WebhookDispatcher:
    """
    Outbound webhook event dispatcher.
    Signs payloads with HMAC-SHA256, delivers with retries, and supports signature validation.
    """

    @classmethod
    def dispatch_event(
        cls,
        event_name: str,
        payload: Dict[str, Any],
        db_path: Optional[str] = None
    ) -> None:
        """
        Query matching subscriptions and asynchronously deliver the event payload.
        """
        try:
            from backend.database.db import list_webhook_subscriptions
            subs = list_webhook_subscriptions(event=event_name, active_only=True, db_path=db_path)
            if not subs:
                return

            event_data = {
                "event": event_name,
                "timestamp": payload.get("timestamp") or time.strftime("%Y-%m-%d %H:%M:%S"),
                "data": payload
            }
            body_bytes = json.dumps(event_data, default=str).encode("utf-8")

            for sub in subs:
                _WEBHOOK_EXECUTOR.submit(cls._deliver_with_retries, sub["target_url"], sub["secret_token"], event_name, body_bytes, sub.get("id"))

        except Exception as e:
            logger.warning(f"Error preparing webhook dispatch for '{event_name}': {e}")

    @classmethod
    def _deliver_with_retries(
        cls,
        target_url: str,
        secret_token: str,
        event_name: str,
        body_bytes: bytes,
        sub_id: Optional[int] = None,
        max_retries: int = 3
    ) -> bool:
        """Deliver payload to target_url with HMAC-SHA256 signature and retry logic."""
        attempt = 0
        while attempt < max_retries:
            attempt += 1
            success = cls._deliver_webhook(target_url, secret_token, event_name, body_bytes, sub_id=sub_id, attempt=attempt)
            if success:
                return True
            if attempt < max_retries:
                time.sleep(0.5 * attempt)  # Backoff between attempts
        logger.warning(f"Webhook delivery to {target_url} failed after {max_retries} attempts.")
        return False

    @classmethod
    def _deliver_webhook(cls, target_url: str, secret_token: str, event_name: str, body_bytes: bytes, sub_id: Optional[int] = None, attempt: int = 1) -> bool:
        """Deliver a single attempt to target_url with HMAC-SHA256 signature and record delivery log."""
        status_code = None
        success = False
        resp_body = ""
        try:
            sig = cls.compute_signature(secret_token, body_bytes)
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "VeriDoc-AI-Webhook/2.0",
                "X-VeriDoc-Event": event_name,
                "X-VeriDoc-Signature": f"sha256={sig}"
            }
            req = urllib.request.Request(target_url, data=body_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=5) as response:
                status_code = response.getcode()
                resp_body = response.read(1024).decode("utf-8", errors="ignore")
                if 200 <= status_code < 300:
                    logger.debug(f"Webhook delivered to {target_url} for event {event_name} (HTTP {status_code})")
                    success = True
                else:
                    logger.warning(f"Webhook delivery to {target_url} returned HTTP {status_code}")
                    success = False
        except Exception as exc:
            logger.debug(f"Webhook delivery attempt failed for {target_url}: {exc}")
            resp_body = str(exc)
            success = False
        finally:
            try:
                from backend.database.db import get_db_connection
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO webhook_deliveries (subscription_id, event_name, payload, status_code, attempt, success, response_body)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                """, (
                    sub_id,
                    event_name,
                    body_bytes.decode("utf-8", errors="ignore") if isinstance(body_bytes, bytes) else str(body_bytes),
                    status_code,
                    attempt,
                    success,
                    resp_body[:1000]
                ))
                conn.commit()
                conn.close()
            except Exception:
                pass
        return success

    @classmethod
    def compute_signature(cls, secret_token: str, body_bytes: bytes) -> str:
        """Compute HMAC-SHA256 hex digest for payload using secret token."""
        return hmac.new(secret_token.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

    @classmethod
    def verify_signature(cls, secret_token: str, body_bytes: bytes, signature_header: str) -> bool:
        """
        Verify incoming webhook signature header (format: 'sha256=<hex_digest>')
        using constant-time comparison to protect against timing attacks.
        """
        if not signature_header or not secret_token:
            return False

        header_parts = signature_header.strip().split("=")
        if len(header_parts) != 2 or header_parts[0] != "sha256":
            return False

        provided_sig = header_parts[1].strip()
        expected_sig = cls.compute_signature(secret_token, body_bytes)
        return hmac.compare_digest(provided_sig, expected_sig)
