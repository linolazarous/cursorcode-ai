# apps/api/app/tasks/email.py
"""
Celery email sending tasks for CursorCode AI
Uses Resend (modern, reliable email API) instead of SendGrid.
"""

import logging
from typing import Optional

import resend
from celery import shared_task

from app.core.config import settings

logger = logging.getLogger(__name__)

# Set Resend API key once (from settings)
resend.api_key = settings.RESEND_API_KEY.get_secret_value()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_task(
    self,
    to: str,
    subject: str,
    html: str,
    from_email: Optional[str] = None,
    reply_to: Optional[str] = None,
):
    """
    Celery task to send a single email via Resend.
    
    Args:
        to: Recipient email address
        subject: Email subject line
        html: Full HTML body content
        from_email: Optional override sender (defaults to settings.EMAIL_FROM)
        reply_to: Optional Reply-To header
    
    Retries up to 3 times on failure with exponential backoff.
    """
    try:
        sender = from_email or settings.EMAIL_FROM

        params = {
            "from": sender,
            "to": [to],
            "subject": subject,
            "html": html,
        }

        if reply_to:
            params["reply_to"] = reply_to

        response = resend.Emails.send(params)

        logger.info(
            f"Email sent successfully to {to} | "
            f"Subject: {subject} | "
            f"Resend ID: {response.get('id')}"
        )

        return response.get('id')

    except Exception as exc:
        logger.error(f"Failed to send email to {to}: {exc}", exc_info=True)
        # Retry with exponential backoff (Celery default behavior)
        raise self.retry(exc=exc)
