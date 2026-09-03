"""
SmartCSV – Plan Limits & Quota Enforcement.

Provides per-plan limits and quota checking for uploads and AI usage.
Uses ``config.PLAN_LIMITS`` as the single source of truth.
"""

from __future__ import annotations

from typing import Any

import config
from utils.logger import get_logger

logger = get_logger(__name__)


def get_limits(plan: str) -> dict[str, Any]:
    """Return limits for a given plan.

    Falls back to ``free`` if the plan is unknown.

    Args:
        plan: Plan name (``free``, ``pro``, ``team``).

    Returns:
        Dict of plan limits.
    """
    return config.PLAN_LIMITS.get(plan, config.PLAN_LIMITS["free"])


def check_upload_quota(user_id: str, plan: str) -> dict[str, Any]:
    """Check if a user is within their upload quota.

    Uses created_at-based counting from the uploads table instead of
    a mutable counter, so it's automatically accurate.

    Args:
        user_id: User UUID.
        plan: User's plan name.

    Returns:
        Dict with ``allowed`` (bool), ``used``, ``limit``, ``remaining``.
    """
    from db.uploads import count_user_uploads_this_month

    limits = get_limits(plan)
    used = count_user_uploads_this_month(user_id)
    limit = limits["uploads_per_month"]

    return {
        "allowed": used < limit,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
    }


def check_ai_quota(user_id: str, plan: str) -> dict[str, Any]:
    """Check if a user is within their AI request quota.

    Args:
        user_id: User UUID.
        plan: User's plan name.

    Returns:
        Dict with ``allowed`` (bool), ``used``, ``limit``, ``remaining``.
    """
    from db.llm_usage import count_user_ai_requests_this_month

    limits = get_limits(plan)
    used = count_user_ai_requests_this_month(user_id)
    limit = limits["ai_requests_per_month"]

    # -1 means unlimited (team plan)
    if limit == -1:
        return {
            "allowed": True,
            "used": used,
            "limit": -1,
            "remaining": -1,
        }

    return {
        "allowed": used < limit,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
    }


def check_file_size_quota(file_size_bytes: int, plan: str) -> dict[str, Any]:
    """Check if a file is within the plan's size limit.

    Args:
        file_size_bytes: File size in bytes.
        plan: User's plan name.

    Returns:
        Dict with ``allowed`` (bool), ``size_mb``, ``limit_mb``.
    """
    limits = get_limits(plan)
    limit_mb = limits["max_file_size_mb"]
    size_mb = round(file_size_bytes / (1024 * 1024), 2)

    return {
        "allowed": size_mb <= limit_mb,
        "size_mb": size_mb,
        "limit_mb": limit_mb,
    }


def check_row_limit(row_count: int, plan: str) -> dict[str, Any]:
    """Check if a dataset is within the plan's row limit.

    Args:
        row_count: Number of rows.
        plan: User's plan name.

    Returns:
        Dict with ``allowed`` (bool), ``rows``, ``limit``.
    """
    limits = get_limits(plan)
    limit = limits["max_rows"]

    return {
        "allowed": row_count <= limit,
        "rows": row_count,
        "limit": limit,
    }


def has_feature(plan: str, feature: str) -> bool:
    """Check if a plan includes a specific feature.

    Args:
        plan: Plan name.
        feature: Feature to check (e.g. ``chat``, ``share``, ``api``).

    Returns:
        True if the feature is included.
    """
    limits = get_limits(plan)
    return feature in limits.get("features", [])
