"""
Stripe Billing – Checkout sessions, webhooks, and plan management.

Uses the Stripe Python SDK for:
- Creating checkout sessions for plan upgrades
- Processing webhooks for subscription lifecycle events
- Managing customer portal sessions
"""

from __future__ import annotations

from typing import Any

import config
from utils.logger import get_logger

logger = get_logger(__name__)

# Plan → Stripe Price mapping (set via env vars)
PRICE_MAP: dict[str, str] = {
    "pro": config.STRIPE_PRICE_PRO,
    "team": config.STRIPE_PRICE_TEAM,
}


def _get_stripe():
    """Lazy-import and configure Stripe."""
    try:
        import stripe
    except ImportError:
        raise ImportError("stripe SDK required. Install: pip install stripe")

    if not config.STRIPE_SECRET_KEY:
        raise ValueError("STRIPE_SECRET_KEY is not configured.")

    stripe.api_key = config.STRIPE_SECRET_KEY
    return stripe


def create_checkout_session(
    user_id: str,
    user_email: str,
    plan: str,
    success_url: str = "/billing/success",
    cancel_url: str = "/billing/cancel",
) -> dict[str, Any]:
    """Create a Stripe Checkout session for a plan upgrade.

    Args:
        user_id: Supabase user UUID.
        user_email: User's email for Stripe customer.
        plan: Target plan (``pro`` or ``team``).
        success_url: Redirect URL on success.
        cancel_url: Redirect URL on cancel.

    Returns:
        Dict with ``checkout_url`` and ``session_id``.
    """
    stripe = _get_stripe()
    price_id = PRICE_MAP.get(plan)
    if not price_id:
        raise ValueError(f"Unknown plan: {plan}")

    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        customer_email=user_email,
        client_reference_id=user_id,
        success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel_url,
        metadata={"user_id": user_id, "plan": plan},
    )

    logger.info("Checkout session created: %s for plan %s", session.id, plan)
    return {"checkout_url": session.url, "session_id": session.id}


def create_portal_session(stripe_customer_id: str) -> str:
    """Create a Stripe Customer Portal session.

    Returns:
        Portal URL string.
    """
    stripe = _get_stripe()
    session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url="/",
    )
    return session.url


def handle_webhook_event(payload: bytes, sig_header: str) -> dict[str, str]:
    """Verify and process a Stripe webhook event.

    Args:
        payload: Raw request body.
        sig_header: ``Stripe-Signature`` header value.

    Returns:
        Dict with ``event_type`` and ``status``.
    """
    stripe = _get_stripe()

    if not config.STRIPE_WEBHOOK_SECRET:
        raise ValueError("STRIPE_WEBHOOK_SECRET not configured.")

    event = stripe.Webhook.construct_event(
        payload, sig_header, config.STRIPE_WEBHOOK_SECRET,
    )

    event_type = event["type"]
    logger.info("Stripe webhook: %s", event_type)

    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("client_reference_id") or session["metadata"].get("user_id")
        plan = session["metadata"].get("plan", "pro")
        customer_id = session.get("customer")

        if user_id:
            from db import users as db_users
            db_users.update_plan(user_id, plan, stripe_customer_id=customer_id)
            logger.info("User %s upgraded to %s", user_id, plan)

    elif event_type in (
        "customer.subscription.deleted",
        "customer.subscription.updated",
    ):
        subscription = event["data"]["object"]
        status = subscription.get("status")
        if status in ("canceled", "unpaid"):
            customer_id = subscription.get("customer")
            logger.info("Subscription %s for customer %s — downgrade needed", status, customer_id)
            # NOTE: For full implementation, look up user by stripe_customer_id
            # and downgrade to 'free'

    return {"event_type": event_type, "status": "processed"}
