"""
Supabase Auth REST API client.

Thin wrapper around Supabase GoTrue endpoints for signup, login,
logout, and user info retrieval.  Uses ``httpx`` for HTTP calls.
"""

from __future__ import annotations

from typing import Any

import httpx

import config
from utils.logger import get_logger

logger = get_logger(__name__)

_TIMEOUT = 10.0  # seconds


def _headers(access_token: str | None = None) -> dict[str, str]:
    """Build request headers for Supabase Auth API."""
    h = {
        "apikey": config.SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
    }
    if access_token:
        h["Authorization"] = f"Bearer {access_token}"
    return h


def _auth_url(path: str) -> str:
    """Construct full Supabase Auth URL."""
    base = config.SUPABASE_URL.rstrip("/")
    return f"{base}/auth/v1{path}"


def sign_up(email: str, password: str) -> dict[str, Any]:
    """Register a new user.

    Args:
        email: User email.
        password: User password (min 6 chars enforced by Supabase).

    Returns:
        Supabase response dict with user and session data.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    resp = httpx.post(
        _auth_url("/signup"),
        json={"email": email, "password": password},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    logger.info("Supabase signup: %s", email)
    return data


def sign_in(email: str, password: str) -> dict[str, Any]:
    """Authenticate an existing user.

    Args:
        email: User email.
        password: User password.

    Returns:
        Supabase response dict with ``access_token``, ``refresh_token``, etc.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    resp = httpx.post(
        _auth_url("/token?grant_type=password"),
        json={"email": email, "password": password},
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    logger.info("Supabase sign-in: %s", email)
    return data


def sign_out(access_token: str) -> None:
    """Revoke a user's session.

    Args:
        access_token: The JWT access token to revoke.
    """
    resp = httpx.post(
        _auth_url("/logout"),
        headers=_headers(access_token),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    logger.info("Supabase sign-out OK")


def get_user(access_token: str) -> dict[str, Any]:
    """Retrieve the authenticated user's profile.

    Args:
        access_token: Valid JWT access token.

    Returns:
        User profile dict.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    resp = httpx.get(
        _auth_url("/user"),
        headers=_headers(access_token),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()
