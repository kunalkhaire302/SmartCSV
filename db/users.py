"""
CRUD operations for the ``users`` table.
"""

from __future__ import annotations

from typing import Any

from db import connection
from utils.logger import get_logger

logger = get_logger(__name__)

TABLE = "users"


def get_user(user_id: str) -> dict[str, Any] | None:
    """Fetch a user by ID.

    Returns:
        User dict or None.
    """
    rows = connection.select(TABLE, filters={"id": f"eq.{user_id}"}, limit=1)
    return rows[0] if rows else None


def get_user_plan(user_id: str) -> str:
    """Return the user's plan name (``free``, ``pro``, ``team``).

    Defaults to ``free`` if the user record is not found.
    """
    user = get_user(user_id)
    return user.get("plan", "free") if user else "free"


def increment_upload_count(user_id: str) -> int:
    """Increment the user's monthly upload counter.

    Returns:
        New upload count.
    """
    user = get_user(user_id)
    if not user:
        return 0

    new_count = user.get("uploads_this_month", 0) + 1
    connection.update(
        TABLE,
        filters={"id": f"eq.{user_id}"},
        data={"uploads_this_month": new_count, "updated_at": "now()"},
    )
    logger.info("User %s upload count -> %d", user_id, new_count)
    return new_count


def update_plan(user_id: str, plan: str, stripe_customer_id: str | None = None) -> None:
    """Update a user's subscription plan.

    Args:
        user_id: User UUID.
        plan: New plan (``free``, ``pro``, ``team``).
        stripe_customer_id: Stripe customer ID (optional).
    """
    data: dict[str, Any] = {"plan": plan, "updated_at": "now()"}
    if stripe_customer_id:
        data["stripe_customer_id"] = stripe_customer_id

    connection.update(TABLE, filters={"id": f"eq.{user_id}"}, data=data)
    logger.info("User %s plan -> %s", user_id, plan)


def reset_monthly_uploads(user_id: str) -> None:
    """Reset the monthly upload counter for a user."""
    connection.update(
        TABLE,
        filters={"id": f"eq.{user_id}"},
        data={
            "uploads_this_month": 0,
            "month_reset_at": "now() + INTERVAL '1 month'",
            "updated_at": "now()",
        },
    )
