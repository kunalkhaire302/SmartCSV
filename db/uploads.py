"""
Domain-specific repository for the ``uploads`` table.

All queries enforce user ownership where applicable.
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


def get_user_dataset(user_id: str, dataset_id: str) -> dict[str, Any] | None:
    """Get a specific upload record, verified to belong to the user.

    This is the primary ownership-verified accessor.

    Args:
        user_id: Authenticated user UUID.
        dataset_id: Upload record UUID.

    Returns:
        Upload dict or None if not found or not owned by user.
    """
    rows = connection.select(
        TABLE,
        filters={"id": f"eq.{dataset_id}", "user_id": f"eq.{user_id}"},
        limit=1,
    )
    return rows[0] if rows else None


def get_upload_by_id(upload_id: str) -> dict[str, Any] | None:
    """Get an upload record by ID (no ownership check — use for internal lookups only).

    Args:
        upload_id: Upload record UUID.

    Returns:
        Upload dict or None.
    """
    rows = connection.select(
        TABLE,
        filters={"id": f"eq.{upload_id}"},
        limit=1,
    )
    return rows[0] if rows else None


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


def get_user_upload_by_key(user_id: str, storage_key: str) -> dict[str, Any] | None:
    """Find an upload record by storage key, verified to belong to the user.

    Args:
        user_id: Authenticated user UUID.
        storage_key: The upload storage key.

    Returns:
        Upload dict or None.
    """
    rows = connection.select(
        TABLE,
        filters={
            "storage_key": f"eq.{storage_key}",
            "user_id": f"eq.{user_id}",
        },
        limit=1,
    )
    return rows[0] if rows else None


def get_user_upload_by_processed_key(user_id: str, processed_key: str) -> dict[str, Any] | None:
    """Find an upload record by processed key, verified to belong to the user.

    Args:
        user_id: Authenticated user UUID.
        processed_key: The processed storage key.

    Returns:
        Upload dict or None.
    """
    rows = connection.select(
        TABLE,
        filters={
            "processed_key": f"eq.{processed_key}",
            "user_id": f"eq.{user_id}",
        },
        limit=1,
    )
    return rows[0] if rows else None


def delete_upload(upload_id: str, user_id: str) -> bool:
    """Delete an upload record (owner only).

    Args:
        upload_id: Upload UUID.
        user_id: Owner user UUID.

    Returns:
        True if deleted.
    """
    try:
        connection.delete(
            TABLE,
            filters={"id": f"eq.{upload_id}", "user_id": f"eq.{user_id}"},
        )
        logger.info("Deleted upload %s for user %s", upload_id, user_id)
        return True
    except Exception as exc:
        logger.warning("Failed to delete upload: %s", exc)
        return False


def count_user_uploads_this_month(user_id: str) -> int:
    """Count uploads created this calendar month for a user.

    Uses created_at-based counting instead of a mutable counter,
    making it automatically correct without needing manual resets.

    Args:
        user_id: User UUID.

    Returns:
        Number of uploads this month.
    """
    try:
        rows = connection.select(
            TABLE,
            filters={
                "user_id": f"eq.{user_id}",
                "created_at": "gte.now()-interval '1 month'",
            },
            limit=1000,
            columns="id",
        )
        return len(rows)
    except Exception as exc:
        logger.warning("Failed to count monthly uploads: %s", exc)
        return 0
