"""
Usage quota enforcement for per-plan upload limits.
"""

from __future__ import annotations

from flask import g, jsonify

from db import users as db_users
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Plan limits ────────────────────────────────────────────────────────

PLAN_LIMITS: dict[str, dict] = {
    "free": {
        "uploads_per_month": 10,
        "max_file_size_mb": 5,
        "ai_summaries_per_month": 3,
    },
    "pro": {
        "uploads_per_month": 100,
        "max_file_size_mb": 50,
        "ai_summaries_per_month": 50,
    },
    "team": {
        "uploads_per_month": 500,
        "max_file_size_mb": 100,
        "ai_summaries_per_month": -1,  # unlimited
    },
}


def get_limits(plan: str) -> dict:
    """Return limits for a plan, defaulting to free."""
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


def check_upload_quota() -> tuple | None:
    """Check if the current user (``g.user_id``) has reached their upload limit.

    Returns:
        ``None`` if within quota, or a ``(response, status_code)`` tuple
        that the caller can return directly to block the request.
    """
    user_id = getattr(g, "user_id", None)
    if not user_id:
        return None  # no auth context — skip quota check

    try:
        plan = db_users.get_user_plan(user_id)
        limits = get_limits(plan)
        user = db_users.get_user(user_id)

        if not user:
            return None  # no user record yet — allow

        current = user.get("uploads_this_month", 0)
        max_uploads = limits["uploads_per_month"]

        if current >= max_uploads:
            logger.warning(
                "User %s exceeded upload quota (%d/%d, plan=%s)",
                user_id, current, max_uploads, plan,
            )
            return jsonify({
                "error": f"Upload limit reached ({max_uploads}/month on {plan} plan).",
                "upgrade_url": "/billing/checkout",
                "current_plan": plan,
            }), 429

    except Exception as exc:
        # Don't block uploads if quota check fails
        logger.warning("Quota check failed (allowing upload): %s", exc)

    return None
