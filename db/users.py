"""
Domain-specific repository for the ``users`` table.
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


def get_user_by_stripe_customer(stripe_customer_id: str) -> dict[str, Any] | None:
    """Look up a user by their Stripe customer ID.

    Used by webhook handlers to find the user associated with
    a Stripe subscription event.

    Args:
        stripe_customer_id: Stripe customer ID.

    Returns:
        User dict or None.
    """
    rows = connection.select(
        TABLE,
        filters={"stripe_customer_id": f"eq.{stripe_customer_id}"},
        limit=1,
    )
    return rows[0] if rows else None


def update_plan(
    user_id: str,
    plan: str,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    stripe_subscription_status: str | None = None,
) -> None:
    """Update a user's subscription plan and Stripe metadata.

    Args:
        user_id: User UUID.
        plan: New plan (``free``, ``pro``, ``team``).
        stripe_customer_id: Stripe customer ID (optional).
        stripe_subscription_id: Stripe subscription ID (optional).
        stripe_subscription_status: Stripe subscription status (optional).
    """
    data: dict[str, Any] = {"plan": plan, "updated_at": "now()"}
    if stripe_customer_id:
        data["stripe_customer_id"] = stripe_customer_id
    if stripe_subscription_id:
        data["stripe_subscription_id"] = stripe_subscription_id
    if stripe_subscription_status:
        data["stripe_subscription_status"] = stripe_subscription_status

    connection.update(TABLE, filters={"id": f"eq.{user_id}"}, data=data)
    logger.info("User %s plan -> %s", user_id, plan)


def increment_upload_count(user_id: str) -> int:
    """Increment the user's monthly upload counter.

    Note: This is a legacy compatibility method. The authoritative
    monthly count is now derived from ``uploads.created_at`` via
    ``db.uploads.count_user_uploads_this_month()``.

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
    return new_count
