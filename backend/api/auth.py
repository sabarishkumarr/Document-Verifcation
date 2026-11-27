import os
from functools import wraps
from flask import request, jsonify, g, current_app
from typing import Optional, List, Callable

from backend.database.db import validate_api_key


def require_api_key(required_scopes: Optional[List[str]] = None) -> Callable:
    """
    Decorator enforcing M2M API key authentication and scope authorization.
    Looks for API key in 'X-API-Key' or 'Authorization: Bearer <key>' header.
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1. Extract API key from headers
            api_key = request.headers.get("X-API-Key")
            if not api_key:
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    api_key = auth_header[7:].strip()

            if not api_key:
                return jsonify({
                    "success": False,
                    "error": "UNAUTHORIZED",
                    "message": "Missing API key. Provide key in 'X-API-Key' or 'Authorization: Bearer <key>' header."
                }), 401

            # 2. Resolve database path from app config
            db_path = None
            try:
                db_path = current_app.config.get("DATABASE_PATH")
            except RuntimeError:
                pass

            # 3. Validate against database
            key_data = validate_api_key(api_key, db_path=db_path)

            # Support configured development override if defined
            dev_key = os.getenv("VERIDOC_DEV_API_KEY") or os.getenv("API_KEY_DEV")
            if not key_data and dev_key and api_key == dev_key:
                key_data = {
                    "id": 0,
                    "key_prefix": api_key[:14],
                    "name": "Dev Override Key",
                    "permissions": ["documents:read", "documents:write", "verification:review", "admin"],
                    "status": "active"
                }

            if not key_data:
                return jsonify({
                    "success": False,
                    "error": "INVALID_API_KEY",
                    "message": "The provided API key is invalid, inactive, or revoked."
                }), 401

            # 4. Scope Authorization Check
            if required_scopes:
                user_perms = key_data.get("permissions", [])
                has_admin = "admin" in user_perms
                if not has_admin:
                    missing_scopes = [s for s in required_scopes if s not in user_perms]
                    if missing_scopes:
                        return jsonify({
                            "success": False,
                            "error": "FORBIDDEN",
                            "message": f"API key lacks required scope(s): {', '.join(missing_scopes)}",
                            "required_scopes": required_scopes
                        }), 403

            # Store validated key context in Flask g for endpoint use
            g.api_key = key_data
            return f(*args, **kwargs)
        return decorated_function
    return decorator
