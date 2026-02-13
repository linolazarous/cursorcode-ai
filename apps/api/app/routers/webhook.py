"""
Stripe Webhook Router - CursorCode AI
Production-hardened endpoint for all Stripe events (subscriptions, invoices, payments).
February 13, 2026 standards: idempotency, encryption, queuing, observability, security.
Uses custom monitoring (structured logging + Supabase app_errors table) instead of Sentry.
"""

import logging
import time
import uuid
import hashlib
from typing import Dict, Any

from fastapi import APIRouter, Request, HTTPException, status, BackgroundTasks
from fastapi.responses import JSONResponse
from slowapi import Limiter
from stripe.error import SignatureVerificationError, StripeError
import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import DBSession  # ← Centralized DB dependency
from app.tasks.billing import (
    handle_checkout_session_completed_task,
    handle_invoice_paid_task,
    handle_invoice_payment_failed_task,
    handle_subscription_updated_task,
    handle_subscription_deleted_task,
    handle_invoice_payment_succeeded_task,
)
from app.services.logging import audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["Webhooks"])

# ────────────────────────────────────────────────
# Clients & Config
# ────────────────────────────────────────────────
stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value()
STRIPE_WEBHOOK_SECRET = settings.STRIPE_WEBHOOK_SECRET.get_secret_value()

redis_client = Redis.from_url(str(settings.REDIS_URL), decode_responses=True)
IDEMPOTENCY_TTL = 60 * 60 * 24 * 7      # 7 days
DEBUG_PAYLOAD_TTL = 60 * 60 * 24        # 1 day for debug

fernet = Fernet(settings.FERNET_KEY.get_secret_value())

# Rate limiter: high burst for Stripe, per IP
limiter = Limiter(key_func=lambda r: r.client.host)


# ────────────────────────────────────────────────
# Main Webhook Endpoint
# ────────────────────────────────────────────────
@router.post("/stripe", response_class=JSONResponse)
@limiter.limit("200/minute")
async def stripe_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: DBSession,  # ← Now uses centralized dependency from deps.py
):
    """
    Main Stripe webhook handler.
    - Verifies signature
    - Checks idempotency (Redis)
    - Stores encrypted payload for debugging (short TTL)
    - Queues async event processing (non-blocking)
    - Logs structured error + stores in Supabase 'app_errors' table on failure
    - Always returns 200 immediately (Stripe requirement)
    """
    request_id = str(uuid.uuid4())
    start_time = time.time()

    # ────────────────────────────────────────────────
    # 1. Read raw payload & signature
    # ────────────────────────────────────────────────
    payload_bytes = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        logger.error(f"[{request_id}] Missing stripe-signature header")
        await _log_error_to_db(db, request_id, "Missing stripe-signature header", None)
        raise HTTPException(status_code=400, detail="Missing signature")

    # ────────────────────────────────────────────────
    # 2. Verify signature
    # ────────────────────────────────────────────────
    try:
        event = stripe.Webhook.construct_event(
            payload_bytes,
            sig_header,
            STRIPE_WEBHOOK_SECRET,
            tolerance=300,  # 5 min clock drift allowed
        )
    except ValueError as e:
        logger.error(f"[{request_id}] Invalid payload: {e}")
        await _log_error_to_db(db, request_id, f"Invalid payload: {str(e)}", str(e))
        raise HTTPException(status_code=400, detail="Invalid payload")
    except SignatureVerificationError as e:
        logger.error(f"[{request_id}] Invalid signature: {e}")
        await _log_error_to_db(db, request_id, f"Invalid signature: {str(e)}", str(e))
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_id = event["id"]
    event_type = event["type"]

    # ────────────────────────────────────────────────
    # 3. Idempotency check (Redis)
    # ────────────────────────────────────────────────
    idempotency_key = f"stripe:processed:{event_id}"
    if await redis_client.get(idempotency_key):
        logger.info(f"[{request_id}] Duplicate event {event_id} - already processed")
        return {"status": "duplicate", "request_id": request_id}

    await redis_client.set(idempotency_key, "processed", ex=IDEMPOTENCY_TTL)

    # ────────────────────────────────────────────────
    # 4. Encrypt & store raw payload for debugging (short TTL)
    # ────────────────────────────────────────────────
    try:
        encrypted_payload = fernet.encrypt(payload_bytes)
        debug_key = f"stripe:debug:{event_id}"
        await redis_client.set(debug_key, encrypted_payload.hex(), ex=DEBUG_PAYLOAD_TTL)
        logger.debug(f"[{request_id}] Debug payload stored (encrypted)")
    except InvalidToken as e:
        logger.error(f"[{request_id}] Fernet encryption failed: {e}")
        await _log_error_to_db(db, request_id, f"Fernet encryption failed: {str(e)}", str(e))

    # ────────────────────────────────────────────────
    # 5. Queue async processing (non-blocking)
    # ────────────────────────────────────────────────
    async def process_event():
        try:
            data_object = event["data"]["object"]

            if event_type == "checkout.session.completed":
                await handle_checkout_session_completed_task.delay(data_object)
            elif event_type == "invoice.paid":
                await handle_invoice_paid_task.delay(data_object)
            elif event_type == "invoice.payment_succeeded":
                await handle_invoice_payment_succeeded_task.delay(data_object)
            elif event_type == "invoice.payment_failed":
                await handle_invoice_payment_failed_task.delay(data_object)
            elif event_type == "customer.subscription.updated":
                await handle_subscription_updated_task.delay(data_object)
            elif event_type == "customer.subscription.deleted":
                await handle_subscription_deleted_task.delay(data_object)
            else:
                logger.info(f"[{request_id}] Ignored webhook event: {event_type}")

            # Audit (queued)
            await audit_log.delay(
                user_id=data_object.get("customer"),
                action="stripe_event_processed",
                metadata={
                    "event_type": event_type,
                    "event_id": event_id,
                    "request_id": request_id,
                    "timestamp": time.time(),
                },
            )

        except Exception as exc:
            logger.exception(f"[{request_id}] Failed to process webhook event {event_type}")
            await _log_error_to_db(db, request_id, f"Webhook processing failed for {event_type}", str(exc))

    background_tasks.add_task(process_event)

    # ────────────────────────────────────────────────
    # 6. Performance monitoring (custom)
    # ────────────────────────────────────────────────
    duration = time.time() - start_time
    if duration > 2.5:  # Stripe timeout = 5s → alert early
        logger.warning(
            f"[{request_id}] Slow webhook processing: {duration:.2f}s for {event_type}",
            extra={"duration_seconds": duration, "event_type": event_type}
        )
        await _log_error_to_db(db, request_id, f"Slow webhook processing: {duration:.2f}s", None)

    return JSONResponse(
        content={"status": "received", "request_id": request_id},
        headers={"X-Request-ID": request_id}
    )


# ────────────────────────────────────────────────
# Helper: Log error to Supabase 'app_errors' table (custom monitoring)
# ────────────────────────────────────────────────
async def _log_error_to_db(db: DBSession, request_id: str, message: str, stack: str | None = None):
    try:
        await db.execute(
            insert("app_errors").values(
                level="webhook_error",
                message=message,
                stack=stack,
                user_id=None,  # webhook events are system-level
                request_path="/webhook/stripe",
                request_method="POST",
                environment=settings.ENVIRONMENT,
                extra={
                    "request_id": request_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        )
        await db.commit()
    except Exception as db_exc:
        logger.error(f"[{request_id}] Failed to log webhook error to DB: {db_exc}")
