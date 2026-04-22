"""
Email delivery via Resend.
"""
from __future__ import annotations

import logging

import httpx

from fastapi import HTTPException, status

from app.config.settings import get_settings


RESEND_API_URL = "https://api.resend.com/emails"
logger = logging.getLogger(__name__)


def _extract_resend_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return "Email delivery failed."

    if isinstance(payload, dict):
        message = str(payload.get("message") or "").strip()
        if message:
            return message
    return "Email delivery failed."


def send_email_via_resend(*, to_email: str, subject: str, html: str) -> None:
    settings = get_settings()
    if not settings.RESEND_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery is not configured.",
        )
    if not settings.RESEND_FROM_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sender email is not configured.",
        )

    response = httpx.post(
        RESEND_API_URL,
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": settings.RESEND_FROM_EMAIL,
            "to": [to_email],
            "subject": subject,
            "html": html,
        },
        timeout=20.0,
    )

    if response.status_code >= 400:
        error_message = _extract_resend_error_message(response)
        logger.error(
            "Resend email delivery failed with status %s: %s",
            response.status_code,
            error_message,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=error_message,
        )
