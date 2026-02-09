# apps/api/app/routers/billing.py
"""
Billing Router - CursorCode AI
Handles Stripe checkout, subscription management, credit usage, and billing portal.
All endpoints require authentication.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Annotated, Dict

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Request,
)
from sqlalchemy.ext.asyncio import AsyncSession

import stripe
from stripe.error import StripeError

from app.core.config import settings
from app.db.session import get_db
from app.middleware.auth import get_current_user, AuthUser
from app.models.user import User
from app.services.billing import (
    create_or_get_stripe_customer,
    create_checkout_session,
    report_usage,
)
from app.services.logging import audit_log
from app.tasks.email import send_email_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["Billing"])

# Rate limiter (protect against abuse)
limiter = Limiter(key_func=lambda r: r.client.host)

stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value()


# ────────────────────────────────────────────────
# Create Checkout Session (subscribe / upgrade plan)
# ────────────────────────────────────────────────
@router.post("/create-checkout-session")
@limiter.limit("5/minute")  # Prevent abuse
async def create_billing_session(
    request: Request,
    plan: str = "pro",  # starter, standard, pro, premier, ultra
    success_url: str = f"{settings.FRONTEND_URL}/billing/success",
    cancel_url: str = f"{settings.FRONTEND_URL}/billing",
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    Generate Stripe Checkout session for subscription/upgrade.
    Returns session URL to redirect user to.
    """
    valid_plans = ["starter", "standard", "pro", "premier", "ultra"]
    if plan not in valid_plans:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid plan. Valid options: {', '.join(valid_plans)}")

    try:
        user = await db.get(User, current_user.id)
        if not user:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

        session = await create_checkout_session(
            user=user,
            plan=plan,
            success_url=success_url,
            cancel_url=cancel_url,
            db=db,
        )

        audit_log.delay(
            user_id=current_user.id,
            action="billing_checkout_created",
            metadata={"plan": plan, "session_id": session["session_id"]},
            request=request,
        )

        return session

    except StripeError as e:
        logger.error(f"Stripe error: {e}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e.user_message or "Payment service error"))
    except Exception as e:
        logger.exception("Checkout session creation failed")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal error")


# ────────────────────────────────────────────────
# Customer Portal (manage subscriptions, payment methods)
# ────────────────────────────────────────────────
@router.post("/portal")
@limiter.limit("5/minute")
async def create_billing_portal(
    request: Request,
    return_url: str = f"{settings.FRONTEND_URL}/billing",
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    Create Stripe Customer Portal session (manage billing, invoices, etc.).
    """
    try:
        user = await db.get(User, current_user.id)
        if not user or not user.stripe_customer_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No Stripe customer found")

        session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=return_url,
        )

        audit_log.delay(
            user_id=current_user.id,
            action="billing_portal_opened",
            metadata={"session_id": session.id},
            request=request,
        )

        return {"url": session.url}

    except StripeError as e:
        logger.error(f"Stripe portal error: {e}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Billing portal unavailable")
    except Exception as e:
        logger.exception("Portal session creation failed")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal error")


# ────────────────────────────────────────────────
# Get current plan & credits (for dashboard)
# ────────────────────────────────────────────────
@router.get("/status")
async def get_billing_status(
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    Returns user's current plan, credits, subscription status.
    """
    user = await db.get(User, current_user.id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    return {
        "plan": user.plan,
        "credits": user.credits,
        "subscription_status": user.subscription_status,
        "stripe_customer_id": user.stripe_customer_id,
        "stripe_subscription_id": user.stripe_subscription_id,
    }


# ────────────────────────────────────────────────
# Report Grok usage (called from orchestrator after agent run)
# ────────────────────────────────────────────────
@router.post("/usage/report")
@limiter.limit("10/minute")  # Protect against abuse
async def report_grok_usage_endpoint(
    request: Request,
    tokens_used: int = Body(..., embed=True),
    model: str = Body(..., embed=True),
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    Reports Grok token usage to Stripe (metered billing).
    Called internally by orchestration.
    """
    try:
        await report_usage(
            user_id=current_user.id,
            tokens=tokens_used,
            model=model,
            db=db,
        )

        audit_log.delay(
            user_id=current_user.id,
            action="grok_usage_reported",
            metadata={"tokens": tokens_used, "model": model},
            request=request,
        )

        return {"status": "reported", "tokens": tokens_used}

    except Exception as e:
        logger.exception("Failed to report usage")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Usage reporting failed")


# ────────────────────────────────────────────────
# Webhook confirmation test endpoint (for debugging)
# ────────────────────────────────────────────────
@router.get("/webhook/test")
async def test_webhook_connection(
    current_user: Annotated[AuthUser, Depends(require_admin)],
):
    """
    Simple endpoint to verify webhook URL is reachable from Stripe.
    """
    return {"status": "webhook endpoint reachable", "user": current_user.email}
