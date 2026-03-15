"""
Supabase Postgres connection helper.

Uses ``httpx`` to call the Supabase PostgREST API directly.
This avoids pulling in the heavy ``supabase-py`` SDK.
"""

from __future__ import annotations

from typing import Any

import httpx

import config
from utils.logger import get_logger

logger = get_logger(__name__)

_TIMEOUT = 10.0


def _headers(*, service_role: bool = False) -> dict[str, str]:
    """Build headers for Supabase PostgREST requests.

    Args:
        service_role: If True, use service-role key (bypasses RLS).
                      If False, use anon key.
    """
    key = config.SUPABASE_SERVICE_ROLE_KEY if service_role else config.SUPABASE_ANON_KEY
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _rest_url(table: str) -> str:
    """Construct full PostgREST URL for a table."""
    base = config.SUPABASE_URL.rstrip("/")
    return f"{base}/rest/v1/{table}"


def insert(table: str, data: dict[str, Any]) -> dict[str, Any]:
    """Insert a row into *table*.

    Returns:
        The inserted row as a dict.

    Raises:
        httpx.HTTPStatusError: On failure.
    """
    resp = httpx.post(
        _rest_url(table),
        json=data,
        headers=_headers(service_role=True),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else data


def select(
    table: str,
    *,
    filters: dict[str, str] | None = None,
    order: str = "created_at.desc",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Select rows from *table*.

    Args:
        filters: PostgREST filter params, e.g. ``{"user_id": "eq.xxx"}``.
        order: Column ordering.
        limit: Max rows.

    Returns:
        List of row dicts.
    """
    params: dict[str, str] = {"order": order, "limit": str(limit)}
    if filters:
        params.update(filters)

    resp = httpx.get(
        _rest_url(table),
        params=params,
        headers=_headers(service_role=True),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def update(
    table: str, *, filters: dict[str, str], data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Update rows matching *filters*.

    Returns:
        Updated rows.
    """
    resp = httpx.patch(
        _rest_url(table),
        params=filters,
        json=data,
        headers=_headers(service_role=True),
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()
