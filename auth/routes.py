"""
Auth routes Blueprint – signup, login, logout, me.
"""

from __future__ import annotations

import httpx
from flask import Blueprint, jsonify, request

import config
from auth import supabase_client
from auth.decorators import require_auth
from utils.logger import get_logger

logger = get_logger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _check_supabase_config() -> tuple | None:
    """Return a 503 response tuple if Supabase is not configured."""
    if not config.SUPABASE_URL or not config.SUPABASE_ANON_KEY:
        return jsonify({"error": "Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY."}), 503
    return None


@auth_bp.route("/signup", methods=["POST"])
def signup():  # noqa: ANN201
    """Register a new user.

    Request JSON: ``{"email": "...", "password": "..."}``
    """
    err = _check_supabase_config()
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or not data.get("email") or not data.get("password"):
        return jsonify({"error": "Email and password are required."}), 400

    try:
        result = supabase_client.sign_up(data["email"], data["password"])
        return jsonify(result), 201
    except httpx.HTTPStatusError as exc:
        body = exc.response.json() if exc.response.content else {}
        msg = body.get("msg") or body.get("error_description") or str(exc)
        logger.warning("Signup failed: %s", msg)
        return jsonify({"error": msg}), exc.response.status_code
    except Exception as exc:
        logger.exception("Signup error")
        return jsonify({"error": f"Signup failed: {exc}"}), 500


@auth_bp.route("/login", methods=["POST"])
def login():  # noqa: ANN201
    """Authenticate an existing user.

    Request JSON: ``{"email": "...", "password": "..."}``

    Returns access_token, refresh_token, user info.
    """
    err = _check_supabase_config()
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or not data.get("email") or not data.get("password"):
        return jsonify({"error": "Email and password are required."}), 400

    try:
        result = supabase_client.sign_in(data["email"], data["password"])
        return jsonify(result), 200
    except httpx.HTTPStatusError as exc:
        body = exc.response.json() if exc.response.content else {}
        msg = body.get("error_description") or body.get("msg") or str(exc)
        logger.warning("Login failed: %s", msg)
        status = 401 if exc.response.status_code == 400 else exc.response.status_code
        return jsonify({"error": msg}), status
    except Exception as exc:
        logger.exception("Login error")
        return jsonify({"error": f"Login failed: {exc}"}), 500


@auth_bp.route("/logout", methods=["POST"])
@require_auth
def logout():  # noqa: ANN201
    """Revoke the current session. Requires Bearer token."""
    token = request.headers.get("Authorization", "")[7:]
    try:
        supabase_client.sign_out(token)
        return jsonify({"message": "Logged out successfully."}), 200
    except Exception as exc:
        logger.warning("Logout failed: %s", exc)
        return jsonify({"message": "Logged out (token may already be expired)."}), 200


@auth_bp.route("/me", methods=["GET"])
@require_auth
def me():  # noqa: ANN201
    """Return the current user's profile. Requires Bearer token."""
    token = request.headers.get("Authorization", "")[7:]
    try:
        user = supabase_client.get_user(token)
        return jsonify(user), 200
    except httpx.HTTPStatusError as exc:
        return jsonify({"error": "Could not fetch user info."}), exc.response.status_code
    except Exception as exc:
        logger.exception("Get user error")
        return jsonify({"error": str(exc)}), 500
