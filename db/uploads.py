"""
CRUD operations for the ``uploads`` table.
"""

from __future__ import annotations

from typing import Any

from db import connection
from utils.logger import get_logger

logger = get_logger(__name__)

TABLE = "uploads"


def create_upload(
    user_id: str,
    original_name: str,
    storage_key: str,
    row_count: int,
    column_count: int,
    size_bytes: int,
) -> dict[str, Any]:
    """Insert a new upload record.

    Args:
        user_id: Supabase user UUID.
        original_name: Original uploaded filename.
        storage_key: Storage key (e.g. ``uploads/20260315_..._data.csv``).
        row_count: Number of rows in the CSV.
        column_count: Number of columns.
        size_bytes: File size in bytes.

    Returns:
        The created upload row.
    """
    data = {
        "user_id": user_id,
        "original_name": original_name,
        "storage_key": storage_key,
        "row_count": row_count,
        "column_count": column_count,
        "size_bytes": size_bytes,
        "status": "uploaded",
    }
    row = connection.insert(TABLE, data)
    logger.info("Created upload record: %s for user %s", storage_key, user_id)
    return row


def get_user_uploads(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Get all uploads for a user, newest first.

    Args:
        user_id: Supabase user UUID.
        limit: Max records to return.

    Returns:
        List of upload dicts.
    """
    return connection.select(
        TABLE,
        filters={"user_id": f"eq.{user_id}"},
        limit=limit,
    )


def update_upload_status(
    upload_id: str,
    status: str,
    processed_key: str | None = None,
) -> list[dict[str, Any]]:
    """Update the status of an upload.

    Args:
        upload_id: Upload UUID.
        status: New status (``processing``, ``completed``, ``failed``).
        processed_key: Storage key of the processed file (set on completion).

    Returns:
        Updated rows.
    """
    data: dict[str, Any] = {
        "status": status,
        "updated_at": "now()",
    }
    if processed_key:
        data["processed_key"] = processed_key

    result = connection.update(
        TABLE,
        filters={"id": f"eq.{upload_id}"},
        data=data,
    )
    logger.info("Upload %s status -> %s", upload_id, status)
    return result


def get_upload_by_key(storage_key: str) -> dict[str, Any] | None:
    """Find an upload record by storage key.

    Args:
        storage_key: The upload storage key.

    Returns:
        Upload dict or None.
    """
    rows = connection.select(
        TABLE,
        filters={"storage_key": f"eq.{storage_key}"},
        limit=1,
    )
    return rows[0] if rows else None
