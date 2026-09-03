"""
Stripe Billing – Checkout sessions, webhooks, and plan management.

Uses absolute URLs from APP_BASE_URL, handles full subscription lifecycle
including cancellation/downgrade, and records Stripe metadata.
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
) -> dict[str, Any]:
    """Create a Stripe Checkout session for a plan upgrade.

    Uses APP_BASE_URL for absolute redirect URLs.

    Args:
        user_id: Supabase user UUID.
        user_email: User's email for Stripe customer.
        plan: Target plan (``pro`` or ``team``).

    Returns:
        Dict with ``checkout_url`` and ``session_id``.
    """
    stripe = _get_stripe()
    price_id = PRICE_MAP.get(plan)
    if not price_id:
        raise ValueError(f"Unknown plan: {plan}")

    base = config.APP_BASE_URL
    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        customer_email=user_email,
        client_reference_id=user_id,
        success_url=f"{base}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base}/billing/cancel",
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
        return_url=config.APP_BASE_URL,
    )
    return session.url


def handle_webhook_event(payload: bytes, sig_header: str) -> dict[str, str]:
    """Verify and process a Stripe webhook event.

    Handles:
    - checkout.session.completed → upgrade plan
    - customer.subscription.deleted → downgrade to free
    - customer.subscription.updated → check for cancellation
    - invoice.paid → confirm active subscription
    - invoice.payment_failed → flag for follow-up

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
        _handle_checkout_completed(event["data"]["object"])

    elif event_type == "customer.subscription.deleted":
        _handle_subscription_cancelled(event["data"]["object"])

    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(event["data"]["object"])

    elif event_type == "invoice.paid":
        logger.info("Invoice paid for customer %s", event["data"]["object"].get("customer"))

    elif event_type == "invoice.payment_failed":
        customer_id = event["data"]["object"].get("customer")
        logger.warning("Payment failed for customer %s", customer_id)

    return {"event_type": event_type, "status": "processed"}


# ═══════════════════════════════════════════════════════════════════════
#  Webhook Handlers
# ═══════════════════════════════════════════════════════════════════════

def _handle_checkout_completed(session: dict) -> None:
    """Handle a successful checkout → upgrade user plan."""
    from db import users as db_users

    user_id = session.get("client_reference_id") or session.get("metadata", {}).get("user_id")
    plan = session.get("metadata", {}).get("plan", "pro")
    customer_id = session.get("customer")
    subscription_id = session.get("subscription")

    if user_id:
        db_users.update_plan(
            user_id,
            plan,
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription_id,
            stripe_subscription_status="active",
        )
        logger.info("User %s upgraded to %s", user_id, plan)


def _handle_subscription_cancelled(subscription: dict) -> None:
    """Handle subscription cancellation → downgrade to free."""
    from db import users as db_users

    customer_id = subscription.get("customer")
    if not customer_id:
        return

    user = db_users.get_user_by_stripe_customer(customer_id)
    if user:
        db_users.update_plan(
            user["id"],
            "free",
            stripe_subscription_status="canceled",
        )
        logger.info("User %s downgraded to free (subscription cancelled)", user["id"])


def _handle_subscription_updated(subscription: dict) -> None:
    """Handle subscription updates — check for cancellation/unpaid."""
    from db import users as db_users

    status = subscription.get("status")
    customer_id = subscription.get("customer")

    if not customer_id:
        return

    if status in ("canceled", "unpaid", "past_due"):
        user = db_users.get_user_by_stripe_customer(customer_id)
        if user:
            if status == "canceled":
                db_users.update_plan(
                    user["id"],
                    "free",
                    stripe_subscription_status="canceled",
                )
                logger.info("User %s downgraded to free (status: %s)", user["id"], status)
            else:
                # Just update the status, don't downgrade yet for past_due
                db_users.update_plan(
                    user["id"],
                    user.get("plan", "free"),
                    stripe_subscription_status=status,
                )
                logger.warning("User %s subscription status: %s", user["id"], status)
