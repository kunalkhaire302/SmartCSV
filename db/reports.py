"""
CRUD operations for the ``shared_reports`` table.
"""

from __future__ import annotations

import secrets
from typing import Any

from db import connection
from utils.logger import get_logger

logger = get_logger(__name__)

TABLE = "shared_reports"


def _generate_token(length: int = 12) -> str:
    """Generate a URL-safe share token."""
    return secrets.token_urlsafe(length)


def create_share(
    user_id: str,
    processed_key: str,
    title: str | None = None,
    expires_hours: int | None = None,
) -> dict[str, Any]:
    """Create a shareable report link.

    Args:
        user_id: Owner user UUID.
        processed_key: Storage key of the processed CSV.
        title: Optional report title.
        expires_hours: Optional expiry in hours.

    Returns:
        Created share record including ``share_token``.
    """
    data: dict[str, Any] = {
        "user_id": user_id,
        "share_token": _generate_token(),
        "processed_key": processed_key,
        "title": title or processed_key.split("/")[-1],
        "is_public": True,
    }
    if expires_hours:
        data["expires_at"] = f"now() + INTERVAL '{expires_hours} hours'"

    row = connection.insert(TABLE, data)
    logger.info("Created share: %s for %s", row.get("share_token"), processed_key)
    return row


def get_by_token(share_token: str) -> dict[str, Any] | None:
    """Look up a shared report by token.

    Returns:
        Share record or None.
    """
    rows = connection.select(
        TABLE,
        filters={"share_token": f"eq.{share_token}"},
        limit=1,
    )
    return rows[0] if rows else None


def increment_views(share_token: str) -> None:
    """Increment the view counter for a shared report."""
    try:
        report = get_by_token(share_token)
        if report:
            new_count = report.get("view_count", 0) + 1
            connection.update(
                TABLE,
                filters={"share_token": f"eq.{share_token}"},
                data={"view_count": new_count},
            )
    except Exception as exc:
        logger.warning("Failed to increment views: %s", exc)


def get_user_shares(user_id: str) -> list[dict[str, Any]]:
    """Get all shared reports for a user."""
    return connection.select(
        TABLE,
        filters={"user_id": f"eq.{user_id}"},
    )


def delete_share(share_token: str, user_id: str) -> bool:
    """Delete a shared report (owner only).

    Returns:
        True if deleted.
    """
    try:
        # Use the connection module to delete
        import httpx
        import config

        key = config.SUPABASE_SERVICE_ROLE_KEY or config.SUPABASE_ANON_KEY
        base = config.SUPABASE_URL.rstrip("/")
        resp = httpx.delete(
            f"{base}/rest/v1/{TABLE}",
            params={
                "share_token": f"eq.{share_token}",
                "user_id": f"eq.{user_id}",
            },
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("Failed to delete share: %s", exc)
        return False
