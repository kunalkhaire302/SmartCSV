"""
Domain-specific repository for the ``shared_reports`` table.
"""

from __future__ import annotations

import secrets
from typing import Any

from db import connection
from utils.logger import get_logger

logger = get_logger(__name__)

TABLE = "shared_reports"


def create_share(
    user_id: str,
    processed_key: str,
    title: str | None = None,
    expires_at: str | None = None,
) -> dict[str, Any]:
    """Create a new shared report.

    Args:
        user_id: Owner user UUID.
        processed_key: Storage key of the processed file.
        title: Optional report title.
        expires_at: Optional expiry timestamp (ISO 8601).

    Returns:
        The created share record.
    """
    share_token = secrets.token_urlsafe(24)

    data: dict[str, Any] = {
        "user_id": user_id,
        "share_token": share_token,
        "processed_key": processed_key,
        "is_public": True,
    }
    if title:
        data["title"] = title
    if expires_at:
        data["expires_at"] = expires_at

    row = connection.insert(TABLE, data)
    logger.info("Created share %s for user %s", share_token, user_id)
    return row


def get_share_by_token(share_token: str) -> dict[str, Any] | None:
    """Look up a share by its public token.

    Args:
        share_token: The unique share token.

    Returns:
        Share dict or None.
    """
    rows = connection.select(
        TABLE,
        filters={"share_token": f"eq.{share_token}", "is_public": "eq.true"},
        limit=1,
    )
    return rows[0] if rows else None


def get_user_shares(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Get all shares for a user.

    Args:
        user_id: Owner user UUID.
        limit: Max records.

    Returns:
        List of share dicts.
    """
    return connection.select(
        TABLE,
        filters={"user_id": f"eq.{user_id}"},
        limit=limit,
    )


def increment_views(share_token: str) -> None:
    """Atomically increment the view count for a shared report.

    Uses SQL increment to avoid read-then-write race condition.
    """
    try:
        # Use rpc for atomic increment
        connection.rpc("increment_share_views", {"p_share_token": share_token})
        logger.debug("Incremented views for share %s", share_token)
    except Exception:
        # Fallback: PostgREST doesn't support SQL expressions in PATCH,
        # so we do a two-step read-then-write as a degraded path.
        share = get_share_by_token(share_token)
        if share:
            new_count = share.get("view_count", 0) + 1
            connection.update(
                TABLE,
                filters={"share_token": f"eq.{share_token}"},
                data={"view_count": new_count},
            )
            logger.debug("Incremented views for share %s (fallback)", share_token)


def revoke_share(share_token: str, user_id: str) -> bool:
    """Revoke (set is_public=false) a share. Owner only.

    Args:
        share_token: Token to revoke.
        user_id: Owner user UUID.

    Returns:
        True if revoked.
    """
    try:
        connection.update(
            TABLE,
            filters={"share_token": f"eq.{share_token}", "user_id": f"eq.{user_id}"},
            data={"is_public": False},
        )
        logger.info("Revoked share %s by user %s", share_token, user_id)
        return True
    except Exception as exc:
        logger.warning("Failed to revoke share: %s", exc)
        return False


def delete_share(share_token: str, user_id: str) -> bool:
    """Delete a share. Owner only.

    Args:
        share_token: Token to delete.
        user_id: Owner user UUID.

    Returns:
        True if deleted.
    """
    try:
        connection.delete(
            TABLE,
            filters={"share_token": f"eq.{share_token}", "user_id": f"eq.{user_id}"},
        )
        logger.info("Deleted share %s by user %s", share_token, user_id)
        return True
    except Exception as exc:
        logger.warning("Failed to delete share: %s", exc)
        return False
