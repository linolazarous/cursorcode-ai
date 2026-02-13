"""
Celery tasks for processing Stripe webhook events.
All tasks are idempotent where possible and include retries.
"""

import logging
from typing import Dict, Any, Optional

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.db.models.user import User
from app.core.config import settings
from app.services.logging import audit_log
from app.services.email import send_email, send_low_credits_alert

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="app.tasks.billing.handle_checkout_session_completed",
    max_retries=5,
    default_retry_delay=30,
    retry_backoff=True,
    retry_jitter=True,
    acks_late=True,
)
def handle_checkout_session_completed_task(
    self,
    session_data: Dict[str, Any],  # required - first
    user_id: Optional[str] = None,
    action: str = "subscription_activated",
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Process successful checkout session (new subscription created).
    Idempotent: safe to re-run.
    """
    if metadata is None:
        metadata = {}

    customer_id = session_data["customer"]
    subscription_id = session_data["subscription"]
    plan = session_data.get("metadata", {}).get("plan", "starter")

    async def _process(db: AsyncSession):
        user = await db.scalar(select(User).where(User.stripe_customer_id == customer_id))
        if not user:
            logger.warning(f"No user found for Stripe customer {customer_id}")
            return

        # Idempotency: skip if already processed
        if user.stripe_subscription_id == subscription_id and user.subscription_status == "active":
            logger.info(f"Subscription {subscription_id} already active for user {user.id}")
            return

        # Update user
        user.stripe_subscription_id = subscription_id
        user.plan = plan
        user.credits += settings.STRIPE_PLAN_CREDITS.get(plan, 75)
        user.subscription_status = "active"
        user.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(user)

        logger.info(
            f"Activated subscription {subscription_id} for user {user.id}",
            extra={"plan": plan, "credits_added": settings.STRIPE_PLAN_CREDITS.get(plan, 75)}
        )

        audit_log.delay(
            user_id=str(user.id),
            action=action,
            metadata=metadata
        )

        # Welcome email
        send_email(
            to=user.email,
            subject="Welcome to CursorCode AI – Subscription Active!",
            html=f"""
            <h2>Welcome aboard!</h2>
            <p>Your {plan.capitalize()} plan is now active.</p>
            <p>You received {settings.STRIPE_PLAN_CREDITS.get(plan, 75)} credits.</p>
            <p><a href="{settings.FRONTEND_URL}/dashboard">Start Building</a></p>
            """
        )

    try:
        with async_session_factory() as db:
            _process(db)
    except Exception as exc:
        logger.exception("Failed to process checkout.session.completed")
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name="app.tasks.billing.handle_invoice_paid",
    max_retries=5,
    default_retry_delay=30,
    retry_backoff=True,
    acks_late=True,
)
def handle_invoice_paid_task(
    self,
    invoice_data: Dict[str, Any],  # required - first
    user_id: Optional[str] = None,
    action: str = "invoice_paid",
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Monthly (or recurring) payment succeeded → reset/add credits.
    """
    if metadata is None:
        metadata = {}

    customer_id = invoice_data["customer"]
    subscription_id = invoice_data["subscription"]

    async def _process(db: AsyncSession):
        user = await db.scalar(select(User).where(User.stripe_customer_id == customer_id))
        if not user or user.stripe_subscription_id != subscription_id:
            logger.warning(f"Mismatched subscription {subscription_id} for customer {customer_id}")
            return

        credits_to_add = settings.STRIPE_PLAN_CREDITS.get(user.plan, 75)
        user.credits += credits_to_add
        user.subscription_status = "active"
        user.updated_at = datetime.now(timezone.utc)

        await db.commit()

        logger.info(
            f"Invoice paid → added {credits_to_add} credits to user {user.id}",
            extra={"subscription_id": subscription_id}
        )

        audit_log.delay(
            user_id=str(user.id),
            action=action,
            metadata=metadata
        )

        # Renewal notification
        send_email(
            to=user.email,
            subject="Subscription Renewed – Credits Added!",
            html=f"""
            <p>Your subscription has renewed successfully.</p>
            <p>You received {credits_to_add} credits for the next billing period.</p>
            """
        )

    try:
        with async_session_factory() as db:
            _process(db)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name="app.tasks.billing.handle_invoice_payment_failed",
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
    retry_backoff=True,
)
def handle_invoice_payment_failed_task(
    self,
    invoice_data: Dict[str, Any],  # required - first
    user_id: Optional[str] = None,
    action: str = "payment_failed",
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Payment failed → mark status, notify user (dunning flow)
    """
    if metadata is None:
        metadata = {}

    customer_id = invoice_data["customer"]
    subscription_id = invoice_data["subscription"]
    attempt_count = invoice_data.get("attempt_count", 1)

    async def _process(db: AsyncSession):
        user = await db.scalar(select(User).where(User.stripe_customer_id == customer_id))
        if not user:
            return

        user.subscription_status = "past_due"
        await db.commit()

        logger.warning(
            f"Payment failed (attempt {attempt_count}) for user {user.id}",
            extra={"subscription_id": subscription_id}
        )

        audit_log.delay(
            user_id=str(user.id),
            action=action,
            metadata=metadata
        )

        # Dunning email
        send_email(
            to=user.email,
            subject=f"Payment Failed – Action Required (Attempt {attempt_count})",
            html=f"""
            <h2>Payment Failed</h2>
            <p>We couldn't process your payment (attempt {attempt_count}).</p>
            <p>Please <a href="{settings.FRONTEND_URL}/billing/update-payment">update your payment method</a> to avoid service interruption.</p>
            <p>Your account will be downgraded in 7 days if unresolved.</p>
            """
        )

    try:
        with async_session_factory() as db:
            _process(db)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name="app.tasks.billing.handle_invoice_payment_succeeded",
    max_retries=5,
    default_retry_delay=30,
    retry_backoff=True,
    acks_late=True,
)
def handle_invoice_payment_succeeded_task(
    self,
    invoice_data: Dict[str, Any],  # required - first
    user_id: Optional[str] = None,
    action: str = "invoice_payment_succeeded",
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Invoice payment succeeded (non-recurring or one-time charge).
    Usually same as paid, but kept separate for potential custom logic.
    """
    if metadata is None:
        metadata = {}

    customer_id = invoice_data["customer"]
    subscription_id = invoice_data["subscription"]

    async def _process(db: AsyncSession):
        user = await db.scalar(select(User).where(User.stripe_customer_id == customer_id))
        if not user or user.stripe_subscription_id != subscription_id:
            logger.warning(f"Mismatched subscription {subscription_id} for customer {customer_id}")
            return

        # Typically same as paid - add credits if needed
        credits_to_add = settings.STRIPE_PLAN_CREDITS.get(user.plan, 75)
        user.credits += credits_to_add
        user.subscription_status = "active"
        user.updated_at = datetime.now(timezone.utc)

        await db.commit()

        logger.info(
            f"Invoice payment succeeded → added {credits_to_add} credits to user {user.id}",
            extra={"subscription_id": subscription_id}
        )

        audit_log.delay(
            user_id=str(user.id),
            action=action,
            metadata=metadata
        )

        # Notify using generic send_email
        send_email(
            to=user.email,
            subject="Payment Succeeded – Invoice Paid",
            html=f"""
            <p>Your recent payment was successful.</p>
            <p>Subscription remains active. Thank you!</p>
            """
        )

    try:
        with async_session_factory() as db:
            _process(db)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name="app.tasks.billing.handle_subscription_updated",
    max_retries=5,
    default_retry_delay=30,
)
def handle_subscription_updated_task(
    self,
    subscription_data: Dict[str, Any],  # required - first
    user_id: Optional[str] = None,
    action: str = "subscription_updated",
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Subscription status / plan changed (active → past_due → trialing → canceled, etc.)
    """
    if metadata is None:
        metadata = {}

    customer_id = subscription_data["customer"]
    new_status = subscription_data["status"]
    subscription_id = subscription_data["id"]

    async def _process(db: AsyncSession):
        user = await db.scalar(select(User).where(User.stripe_customer_id == customer_id))
        if not user or user.stripe_subscription_id != subscription_id:
            return

        if user.subscription_status == new_status:
            return  # idempotent

        user.subscription_status = new_status
        await db.commit()

        logger.info(
            f"Subscription {subscription_id} updated to {new_status} for user {user.id}"
        )

        audit_log.delay(
            user_id=str(user.id),
            action=action,
            metadata=metadata
        )

        # Notify on important changes
        if new_status in ["past_due", "canceled", "unpaid"]:
            send_email(
                to=user.email,
                subject=f"Your Subscription is {new_status.capitalize()}",
                html=f"""
                <p>Your subscription status changed to <strong>{new_status}</strong>.</p>
                <p>Please <a href="{settings.FRONTEND_URL}/billing">review your billing</a> to resolve.</p>
                """
            )

    try:
        with async_session_factory() as db:
            _process(db)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name="app.tasks.billing.handle_subscription_deleted",
    max_retries=3,
    default_retry_delay=60,
)
def handle_subscription_deleted_task(
    self,
    subscription_data: Dict[str, Any],  # required - first
    user_id: Optional[str] = None,
    action: str = "subscription_canceled",
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Subscription canceled / deleted → downgrade to free tier
    """
    if metadata is None:
        metadata = {}

    customer_id = subscription_data["customer"]
    subscription_id = subscription_data["id"]

    async def _process(db: AsyncSession):
        user = await db.scalar(select(User).where(User.stripe_customer_id == customer_id))
        if not user or user.stripe_subscription_id != subscription_id:
            return

        user.plan = "starter"
        user.credits = settings.FREE_TIER_CREDITS  # e.g. 10
        user.stripe_subscription_id = None
        user.subscription_status = "canceled"
        await db.commit()

        logger.info(f"Subscription {subscription_id} deleted → downgraded user {user.id} to starter")

        send_email(
            to=user.email,
            subject="Your CursorCode AI Subscription Has Been Canceled",
            html=f"""
            <p>Your subscription has been canceled.</p>
            <p>You are now on the free Starter plan with {settings.FREE_TIER_CREDITS} credits.</p>
            <p><a href="{settings.FRONTEND_URL}/billing">Reactivate anytime</a></p>
            """
        )

        audit_log.delay(
            user_id=str(user.id),
            action=action,
            metadata=metadata
        )

    try:
        with async_session_factory() as db:
            _process(db)
    except Exception as exc:
        raise self.retry(exc=exc)
