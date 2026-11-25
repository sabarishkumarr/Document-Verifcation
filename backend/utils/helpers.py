import hashlib
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from flask import jsonify, Response
from werkzeug.utils import secure_filename


def calculate_sha256(file_path: Path | str, chunk_size: int = 65536) -> str:
    """
    Calculate the SHA-256 hash of a file using chunked streaming.
    
    Streaming in chunks prevents loading large documents entirely into RAM.
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def format_response(
    success: bool,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    status_code: int = 200,
    **extra: Any
) -> Tuple[Response, int]:
    """
    Construct a standardized JSON response tuple for Flask endpoints.
    
    Guarantees consistent schema:
    {
        "success": bool,
        "message": str,
        "data": dict (optional),
        ...extra fields
    }
    """
    payload: Dict[str, Any] = {
        "success": success,
        "message": message
    }
    if data is not None:
        payload["data"] = data
    if extra:
        payload.update(extra)
    return jsonify(payload), status_code


def sanitize_filename(filename: str) -> str:
    """
    Sanitize an untrusted user-supplied filename.
    
    Removes directory traversal sequences, null bytes, and non-ASCII/dangerous characters.
    Falls back to a safe generic filename if secure_filename results in an empty string.
    """
    cleaned = secure_filename(filename)
    if not cleaned:
        # Fallback if filename was purely special characters (e.g., "...jpg" or ".png")
        base, ext = os.path.splitext(filename)
        clean_ext = re.sub(r"[^a-zA-Z0-9]", "", ext)
        cleaned = f"upload_{os.urandom(4).hex()}.{clean_ext}" if clean_ext else f"upload_{os.urandom(4).hex()}"
    return cleaned
