"""
Domain-specific repository for the ``llm_usage`` table.

Tracks AI/LLM API calls per user for quota enforcement and analytics.
"""

from __future__ import annotations

from typing import Any

from db import connection
from utils.logger import get_logger

logger = get_logger(__name__)

TABLE = "llm_usage"


def record_usage(
    user_id: str,
    tokens_used: int,
    purpose: str = "summary",
    model: str = "claude-sonnet-4-5",
) -> dict[str, Any]:
    """Record an AI/LLM API call for quota tracking.

    Args:
        user_id: The user who made the request.
        tokens_used: Total tokens consumed (input + output).
        purpose: The type of AI request (``summary``, ``chat``).
        model: Model identifier.

    Returns:
        The created usage record.
    """
    data = {
        "user_id": user_id,
        "tokens_used": tokens_used,
        "purpose": purpose,
        "model": model,
    }
    row = connection.insert(TABLE, data)
    logger.info("Recorded LLM usage: user=%s, purpose=%s, tokens=%d", user_id, purpose, tokens_used)
    return row


def count_user_ai_requests_this_month(user_id: str) -> int:
    """Count AI requests this calendar month for a user.

    Uses created_at-based counting to be automatically correct.

    Args:
        user_id: User UUID.

    Returns:
        Number of AI requests this month.
    """
    try:
        rows = connection.select(
            TABLE,
            filters={
                "user_id": f"eq.{user_id}",
                "created_at": "gte.now()-interval '1 month'",
            },
            limit=10000,
            columns="id",
        )
        return len(rows)
    except Exception as exc:
        logger.warning("Failed to count AI requests: %s", exc)
        return 0


def get_user_usage_summary(user_id: str) -> dict[str, Any]:
    """Get a summary of the user's AI usage for the current month.

    Returns:
        Dict with ``requests_this_month`` and ``tokens_this_month``.
    """
    try:
        rows = connection.select(
            TABLE,
            filters={
                "user_id": f"eq.{user_id}",
                "created_at": "gte.now()-interval '1 month'",
            },
            limit=10000,
            columns="tokens_used",
        )
        total_tokens = sum(r.get("tokens_used", 0) for r in rows)
        return {
            "requests_this_month": len(rows),
            "tokens_this_month": total_tokens,
        }
    except Exception as exc:
        logger.warning("Failed to get usage summary: %s", exc)
        return {"requests_this_month": 0, "tokens_this_month": 0}
