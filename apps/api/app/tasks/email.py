# apps/api/app/tasks/email.py
"""
Celery email sending tasks for CursorCode AI
Uses Resend (modern, reliable email API) instead of SendGrid.
"""

import logging
from typing import Optional, Dict, Any

import resend
from celery import shared_task

from app.core.config import settings
from app.services.logging import audit_log

logger = logging.getLogger(__name__)

# Set Resend API key once (from settings)
resend.api_key = settings.RESEND_API_KEY.get_secret_value()


@shared_task(
    bind=True,
    name="app.tasks.email.send_email",
    max_retries=3,
    default_retry_delay=60,          # initial delay
    retry_backoff=True,              # exponential backoff
    retry_jitter=True,               # random jitter to avoid thundering herd
    acks_late=True,                  # only ack after task completes
)
def send_email_task(
    self,
    to: str,
    subject: str,
    html: str,
    from_email: Optional[str] = None,
    reply_to: Optional[str] = None,
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Celery task to send a single email via Resend.

    Retries up to 3 times on failure with exponential backoff + jitter.
    Logs success/failure and audits the event.

    Args:
        to: Recipient email address
        subject: Email subject line
        html: Full HTML body content
        from_email: Optional override sender (defaults to settings.EMAIL_FROM)
        reply_to: Optional Reply-To header
        cc: Optional list of CC recipients
        bcc: Optional list of BCC recipients
        metadata: Optional dict for audit/logging context

    Returns:
        Resend message ID on success, None on final failure after retries
    """
    sender = from_email or settings.EMAIL_FROM

    params = {
        "from": sender,
        "to": [to],
        "subject": subject,
        "html": html,
    }

    if reply_to:
        params["reply_to"] = reply_to
    if cc:
        params["cc"] = cc
    if bcc:
        params["bcc"] = bcc

    try:
        response = resend.Emails.send(params)

        message_id = response.get("id")

        logger.info(
            f"Email sent successfully",
            extra={
                "to": to,
                "subject": subject,
                "message_id": message_id,
                "provider": "resend",
                "metadata": metadata or {},
            }
        )

        audit_log.delay(
            user_id=None,
            action="email_sent",
            metadata={
                "to": to,
                "subject": subject,
                "message_id": message_id,
                "status": "success",
                "provider": "resend",
                **(metadata or {}),
            }
        )

        return message_id

    except resend.ResendError as e:
        error_detail = str(e)
        logger.error(
            f"Resend API error sending email to {to}",
            extra={
                "subject": subject,
                "error": error_detail,
                "metadata": metadata or {},
            },
            exc_info=True
        )

        audit_log.delay(
            user_id=None,
            action="email_failed",
            metadata={
                "to": to,
                "subject": subject,
                "error": error_detail,
                "provider": "resend",
                **(metadata or {}),
            }
        )

        raise self.retry(exc=e)

    except Exception as exc:
        logger.exception(
            f"Unexpected failure sending email to {to}",
            extra={"subject": subject, "metadata": metadata or {}}
        )

        audit_log.delay(
            user_id=None,
            action="email_failed",
            metadata={
                "to": to,
                "subject": subject,
                "error": str(exc),
                "provider": "resend",
                **(metadata or {}),
            }
        )

        raise self.retry(exc=exc)
