"""
Transactional email delivery.

Supports:
- local capture mode for local-first installs and testing
- Resend for real outbound delivery
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import logging
from pathlib import Path
import re

import httpx

from app.config.settings import get_settings


RESEND_API_URL = "https://api.resend.com/emails"
logger = logging.getLogger(__name__)
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


class EmailDeliveryError(RuntimeError):
    """Raised when the configured mail transport cannot deliver a message."""


@dataclass(frozen=True)
class MailDeliveryResult:
    transport: str
    artifact_path: str | None = None


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


def _subject_slug(subject: str) -> str:
    normalized = _SLUG_PATTERN.sub("-", (subject or "").strip().lower()).strip("-")
    return normalized or "email"


def _send_email_via_resend(*, to_email: str, subject: str, html: str) -> MailDeliveryResult:
    settings = get_settings()
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
        raise EmailDeliveryError("Email delivery is currently unavailable.")

    return MailDeliveryResult(transport="resend")


def _capture_email_locally(*, to_email: str, subject: str, html: str) -> MailDeliveryResult:
    settings = get_settings()
    outbox_dir = Path(settings.resolved_mail_local_outbox_dir)
    outbox_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
    slug = _subject_slug(subject)
    stem = f"{timestamp}-{slug}"
    html_path = outbox_dir / f"{stem}.html"
    json_path = outbox_dir / f"{stem}.json"

    html_path.write_text(html, encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "captured_at": datetime.utcnow().isoformat() + "Z",
                "transport": "local",
                "to": to_email,
                "subject": subject,
                "html_file": html_path.name,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("Captured transactional email locally at %s", json_path)
    return MailDeliveryResult(transport="local", artifact_path=str(json_path))


def send_transactional_email(*, to_email: str, subject: str, html: str) -> MailDeliveryResult:
    transport = get_settings().resolved_mail_transport
    if transport == "resend":
        return _send_email_via_resend(to_email=to_email, subject=subject, html=html)
    return _capture_email_locally(to_email=to_email, subject=subject, html=html)
