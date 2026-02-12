"""
Billing Router - CursorCode AI
Handles Stripe checkout, subscription management, credit usage, and billing portal.
All endpoints require authentication.
"""

import logging
from datetime import datetime
from typing import Annotated, Dict, Literal, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Request,
    Body,
)
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter

import stripe
from stripe.error import StripeError, InvalidRequestError

from app.core.config import settings
from app.db.session import get_db
from app.middleware.auth import get_current_user, AuthUser
from app.db.models.user import User
from app.services.billing import (
    create_or_get_stripe_customer,
    create_checkout_session,
    report_usage,
)
from app.services.logging import audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["Billing"])

security = HTTPBearer(auto_error=False)

# Rate limiter: per authenticated user
def billing_limiter_key(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "id"):
        return str(user.id)
    return request.client.host  # fallback

limiter = Limiter(key_func=billing_limiter_key)

stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value()


# ────────────────────────────────────────────────
# Models
# ────────────────────────────────────────────────
class Plan(str):
    starter = "starter"
    standard = "standard"
    pro = "pro"
    premier = "premier"
    ultra = "ultra"


class CreateCheckoutSessionRequest(BaseModel):
    plan: Plan = Field(...)
    success_url: str = Field(default_factory=lambda: f"{settings.FRONTEND_URL}/billing/success")
    cancel_url: str = Field(default_factory=lambda: f"{settings.FRONTEND_URL}/billing")


class BillingPortalRequest(BaseModel):
    return_url: str = Field(default_factory=lambda: f"{settings.FRONTEND_URL}/billing")


class UsageReportRequest(BaseModel):
    tokens_used: int = Field(..., ge=0)
    model: str = Field(..., min_length=1)


class BillingStatusResponse(BaseModel):
    plan: str
    credits: int
    subscription_status: Optional[str]
    stripe_customer_id: Optional[str]
    stripe_subscription_id: Optional[str]


# ────────────────────────────────────────────────
# Create Checkout Session
# ────────────────────────────────────────────────
@router.post("/create-checkout-session", response_model=dict[str, str])
@limiter.limit("5/minute")
async def create_billing_session(
    request: Request,
    payload: CreateCheckoutSessionRequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await db.get(User, current_user.id)
        if not user:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

        customer_id = await create_or_get_stripe_customer(user, db)

        idempotency_key = f"checkout_{current_user.id}_{payload.plan}_{datetime.utcnow().timestamp()}"

        session = await create_checkout_session(
            user=user,
            plan=payload.plan,
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
            db=db,
            idempotency_key=idempotency_key,
        )

        audit_log.delay(
            user_id=current_user.id,
            action="billing_checkout_created",
            metadata={
                "plan": payload.plan,
                "session_id": session["session_id"],
                "customer_id": customer_id,
                "ip": request.client.host,
            },
            request=request,
        )

        return {"url": session["url"]}

    except StripeError as e:
        logger.error(f"Stripe error during checkout: {e}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment setup failed.")
    except Exception as e:
        logger.exception("Checkout session creation failed")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal error")


# ────────────────────────────────────────────────
# Customer Portal
# ────────────────────────────────────────────────
@router.post("/portal", response_model=dict[str, str])
@limiter.limit("5/minute")
async def create_billing_portal(
    request: Request,
    payload: BillingPortalRequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await db.get(User, current_user.id)
        if not user or not user.stripe_customer_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No Stripe customer found.")

        session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=payload.return_url,
            idempotency_key=f"portal_{current_user.id}_{datetime.utcnow().timestamp()}",
        )

        audit_log.delay(
            user_id=current_user.id,
            action="billing_portal_opened",
            metadata={"session_id": session.id, "ip": request.client.host},
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
# Get current billing status
# ────────────────────────────────────────────────
@router.get("/status", response_model=BillingStatusResponse)
async def get_billing_status(
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, current_user.id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    return BillingStatusResponse(
        plan=user.plan,
        credits=user.credits,
        subscription_status=user.subscription_status,
        stripe_customer_id=user.stripe_customer_id,
        stripe_subscription_id=user.stripe_subscription_id,
    )


# ────────────────────────────────────────────────
# Report Grok usage (internal)
# ────────────────────────────────────────────────
@router.post("/usage/report")
@limiter.limit("20/minute")
async def report_grok_usage_endpoint(
    request: Request,
    payload: UsageReportRequest = Body(...),
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    try:
        await report_usage(
            user_id=current_user.id,
            tokens=payload.tokens_used,
            model=payload.model,
            db=db,
        )

        audit_log.delay(
            user_id=current_user.id,
            action="grok_usage_reported",
            metadata={
                "tokens": payload.tokens_used,
                "model": payload.model,
                "ip": request.client.host,
            },
            request=request,
        )

        return {"status": "reported", "tokens": payload.tokens_used}

    except Exception as e:
        logger.exception("Failed to report usage")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Usage reporting failed")


# ────────────────────────────────────────────────
# Webhook test (admin debug)
# ────────────────────────────────────────────────
@router.get("/webhook/test")
async def test_webhook_connection(
    current_user: Annotated[AuthUser, Depends(require_admin)],
):
    return {
        "status": "webhook endpoint reachable",
        "user": current_user.email,
        "timestamp": datetime.now(ZoneInfo("UTC")).isoformat()
    }
