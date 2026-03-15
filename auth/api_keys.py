"""
API key management – generate, validate, and revoke developer API keys.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

from db import connection
from utils.logger import get_logger

logger = get_logger(__name__)

TABLE = "api_keys"
KEY_PREFIX = "sk_csv_"


def _hash_key(key: str) -> str:
    """SHA-256 hash an API key."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_key(user_id: str, name: str = "Default") -> dict[str, Any]:
    """Generate a new API key for a user.

    Args:
        user_id: Owner user UUID.
        name: Friendly name for the key.

    Returns:
        Dict with ``api_key`` (full key, shown only once) and record metadata.
    """
    raw_key = KEY_PREFIX + secrets.token_urlsafe(32)
    key_hash = _hash_key(raw_key)
    key_prefix = raw_key[:16] + "..."

    row = connection.insert(TABLE, {
        "user_id": user_id,
        "key_hash": key_hash,
        "key_prefix": key_prefix,
        "name": name,
    })

    logger.info("API key created for user %s: %s", user_id, key_prefix)
    row["api_key"] = raw_key  # Only returned at creation time
    return row


def validate_key(api_key: str) -> dict[str, Any] | None:
    """Validate an API key and return the associated user info.

    Args:
        api_key: The raw API key string.

    Returns:
        Key record (including ``user_id``) or None if invalid/inactive.
    """
    key_hash = _hash_key(api_key)
    rows = connection.select(
        TABLE,
        filters={"key_hash": f"eq.{key_hash}", "is_active": "eq.true"},
        limit=1,
    )
    if not rows:
        return None

    # Update last_used_at (best-effort)
    try:
        connection.update(
            TABLE,
            filters={"key_hash": f"eq.{key_hash}"},
            data={"last_used_at": "now()"},
        )
    except Exception:
        pass

    return rows[0]


def list_keys(user_id: str) -> list[dict[str, Any]]:
    """List all API keys for a user (without exposing hashes)."""
    rows = connection.select(TABLE, filters={"user_id": f"eq.{user_id}"})
    for r in rows:
        r.pop("key_hash", None)  # Never expose the hash
    return rows


def revoke_key(key_id: str, user_id: str) -> bool:
    """Deactivate an API key."""
    try:
        connection.update(
            TABLE,
            filters={"id": f"eq.{key_id}", "user_id": f"eq.{user_id}"},
            data={"is_active": False},
        )
        logger.info("API key %s revoked", key_id)
        return True
    except Exception as exc:
        logger.warning("Key revocation failed: %s", exc)
        return False
