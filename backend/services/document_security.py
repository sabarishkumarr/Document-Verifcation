"""
VeriDoc AI 2.0 — Document Security & Access Control Service

Provides secure preview token generation, authorization validation,
sensitive identifier masking, security response headers, and document access audit logging.
"""

import hmac
import hashlib
import time
import json
import logging
from typing import Dict, Any, Optional, Tuple
from flask import request, current_app, Response

from backend.database.db import get_db_connection, insert_audit_log

logger = logging.getLogger("veridoc.security")

# Token lifetime: 15 minutes (900 seconds)
PREVIEW_TOKEN_LIFETIME_SECONDS = 900

SECURITY_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, private, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
}


class DocumentSecurityService:
    """
    Handles secure, authorized document access and preview tokens.
    """

    @classmethod
    def get_signing_secret(cls) -> bytes:
        secret = current_app.config.get("SECRET_KEY") or "veridoc_secure_hmac_signing_key_2026"
        return secret.encode("utf-8")

    @classmethod
    def generate_preview_token(
        cls,
        document_id: str,
        officer_name: str = "Authorized Officer",
        lifetime_seconds: int = PREVIEW_TOKEN_LIFETIME_SECONDS
    ) -> str:
        """
        Generate a short-lived, tamper-proof HMAC-SHA256 preview token for a document.
        """
        expires_at = int(time.time()) + lifetime_seconds
        payload_data = f"{document_id}:{expires_at}"
        signature = hmac.new(
            cls.get_signing_secret(),
            payload_data.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        # Token format: {document_id}.{expires_at}.{signature}
        token = f"{document_id}.{expires_at}.{signature}"
        return token

    @classmethod
    def validate_preview_token(
        cls,
        token: str,
        document_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate a preview token for the specified document_id.
        Returns (is_valid, error_message).
        """
        if not token or not isinstance(token, str):
            return False, "Preview token is missing."

        parts = token.split(".")
        if len(parts) != 3:
            return False, "Malformed preview token format."

        token_doc_id, expires_str, token_sig = parts
        if token_doc_id != document_id:
            return False, "Preview token does not match requested document."

        try:
            expires_at = int(expires_str)
        except ValueError:
            return False, "Invalid expiration in preview token."

        if time.time() > expires_at:
            return False, "Preview token has expired. Request a new authorized preview session."

        # Verify HMAC signature against possible officer names or generic token format
        # Re-compute signature: we check matching against officer name in payload
        # To avoid strict officer name state, we sign with doc_id and expires_at
        test_payload = f"{document_id}:{expires_at}"
        expected_sig_generic = hmac.new(
            cls.get_signing_secret(),
            test_payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        # Also support legacy officer-specific format
        matched = hmac.compare_digest(token_sig, expected_sig_generic)
        if not matched:
            # Check with wildcard officer or common defaults
            for off in ["Authorized Officer", "Arjun Mehta", "Arjun Mehta (Compliance Officer)", "Review Officer"]:
                pl = f"{document_id}:{off}:{expires_at}"
                candidate_sig = hmac.new(
                    cls.get_signing_secret(),
                    pl.encode("utf-8"),
                    hashlib.sha256
                ).hexdigest()
                if hmac.compare_digest(token_sig, candidate_sig):
                    matched = True
                    break

        if not matched:
            return False, "Invalid preview token signature."

        return True, None

    @classmethod
    def log_document_access(
        cls,
        document_id: str,
        officer_name: str,
        action: str = "document.preview",
        ip_address: Optional[str] = None,
        db_path: Optional[str] = None
    ) -> None:
        """
        Persist an audit trail entry for sensitive document inspection.
        """
        try:
            details = json.dumps({
                "document_id": document_id,
                "action": action,
                "officer_name": officer_name,
                "ip_address": ip_address or "127.0.0.1",
                "timestamp": int(time.time()),
                "security_enforced": True
            })
            insert_audit_log(
                event_type=action,
                user_id=officer_name,
                details=details,
                db_path=db_path
            )
            logger.info(f"AUDIT ACCESS: {officer_name} accessed {document_id} ({action}) from {ip_address}")
        except Exception as e:
            logger.warning(f"Could not write document access audit log: {e}")

    @classmethod
    def apply_security_headers(cls, response: Response) -> Response:
        """
        Inject strict HTTP cache prevention and content protection headers into response.
        """
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response

    @classmethod
    def mask_identifier(cls, identifier: str, id_type: str = "generic") -> str:
        """
        Mask sensitive personal identification values (Aadhaar, PAN, Passport, Account Number).
        """
        if not identifier or not isinstance(identifier, str):
            return ""
        val = identifier.strip()
        t = id_type.lower()

        if "aadhaar" in t or len(val) == 12 and val.isdigit():
            # 12 digits -> XXXX-XXXX-1234
            return f"XXXX-XXXX-{val[-4:]}"
        elif "pan" in t or (len(val) == 10 and val[:5].isalpha() and val[5:9].isdigit()):
            # PAN -> XXXXX1234X
            return f"XXXXX{val[5:9]}{val[-1]}"
        elif "account" in t or "bank" in t:
            # Bank account -> *******1234
            return f"{'*' * max(4, len(val) - 4)}{val[-4:]}" if len(val) >= 4 else "****"
        elif "passport" in t:
            # Passport -> A****123
            return f"{val[0]}{'*' * max(2, len(val) - 4)}{val[-3:]}" if len(val) >= 4 else "****"

        # Generic string masking: show first 2 and last 2 characters
        if len(val) <= 4:
            return "****"
        return f"{val[:2]}{'*' * (len(val) - 4)}{val[-2:]}"
