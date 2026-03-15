"""
Billing routes Blueprint – Checkout, webhooks, portal.
"""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from auth.decorators import require_auth
from billing.stripe_client import (
    create_checkout_session,
    create_portal_session,
    handle_webhook_event,
)
from utils.logger import get_logger

logger = get_logger(__name__)

billing_bp = Blueprint("billing", __name__, url_prefix="/billing")


@billing_bp.route("/checkout", methods=["POST"])
@require_auth
def checkout():  # noqa: ANN201
    """Create a Stripe Checkout session.

    Request JSON: ``{"plan": "pro"}``
    """
    data = request.get_json(silent=True)
    if not data or not data.get("plan"):
        return jsonify({"error": "Missing 'plan' in request body."}), 400

    plan = data["plan"]
    if plan not in ("pro", "team"):
        return jsonify({"error": "Plan must be 'pro' or 'team'."}), 400

    try:
        result = create_checkout_session(
            user_id=g.user_id,
            user_email=g.user_email,
            plan=plan,
        )
        return jsonify(result), 200
    except (ImportError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        logger.exception("Checkout failed")
        return jsonify({"error": f"Checkout failed: {exc}"}), 500


@billing_bp.route("/portal", methods=["POST"])
@require_auth
def portal():  # noqa: ANN201
    """Create a Stripe Customer Portal session."""
    try:
        from db import users as db_users
        user = db_users.get_user(g.user_id)
        if not user or not user.get("stripe_customer_id"):
            return jsonify({"error": "No billing account found."}), 404

        url = create_portal_session(user["stripe_customer_id"])
        return jsonify({"portal_url": url}), 200
    except (ImportError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        logger.exception("Portal session failed")
        return jsonify({"error": str(exc)}), 500


@billing_bp.route("/webhook", methods=["POST"])
def webhook():  # noqa: ANN201
    """Stripe webhook endpoint (no auth – verified by Stripe signature)."""
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")

    try:
        result = handle_webhook_event(payload, sig)
        return jsonify(result), 200
    except (ImportError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        logger.warning("Webhook processing failed: %s", exc)
        return jsonify({"error": str(exc)}), 400
