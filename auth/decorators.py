"""
Auth decorators – protect Flask routes with JWT verification.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

import jwt
from jwt import PyJWKClient
from flask import g, jsonify, request
from sentry_sdk import set_user

import config
from utils.logger import get_logger

logger = get_logger(__name__)

# Cache the JWK client to avoid fetching keys on every request
_jwk_client: PyJWKClient | None = None
if config.SUPABASE_JWKS_URL:
    _jwk_client = PyJWKClient(config.SUPABASE_JWKS_URL)

def require_auth(fn: Callable) -> Callable:
    """Decorator that enforces a valid Supabase JWT on the request.

    Reads ``Authorization: Bearer <token>``, verifies the JWT using
    ``SUPABASE_JWT_SECRET``, and sets ``g.user_id`` for downstream use.

    Returns 401 JSON error if the token is missing, expired, or invalid.
    """
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header."}), 401

        token = auth_header[7:]  # strip "Bearer "

        if not config.SUPABASE_JWKS_URL and not config.SUPABASE_JWT_SECRET:
            logger.error("Neither SUPABASE_JWKS_URL nor SUPABASE_JWT_SECRET is configured.")
            return jsonify({"error": "Auth service not configured."}), 503

        try:
            if _jwk_client:
                # Use asymmetric RS256 with JWKS
                signing_key = _jwk_client.get_signing_key_from_jwt(token)
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    audience="authenticated",
                )
            else:
                # Fallback to symmetric HS256 with JWT secret
                payload = jwt.decode(
                    token,
                    config.SUPABASE_JWT_SECRET,
                    algorithms=["HS256"],
                    audience="authenticated",
                )

            g.user_id = payload.get("sub")
            g.user_email = payload.get("email", "")
            g.user_role = payload.get("role", "authenticated")
            set_user({"id": g.user_id})
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired."}), 401
        except jwt.InvalidTokenError as exc:
            logger.warning("Invalid JWT: %s", exc)
            return jsonify({"error": "Invalid token."}), 401

        return fn(*args, **kwargs)

    return wrapper
