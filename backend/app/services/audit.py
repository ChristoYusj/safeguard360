"""
Audit logging helpers.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import AuditLog


AUDIT_LOGIN_SUCCESS = "login_success"
AUDIT_LOGIN_FAILURE = "login_failure"
AUDIT_LOGOUT = "logout"
AUDIT_PASSWORD_CHANGE = "password_change"
AUDIT_TWO_FACTOR_ENABLED = "two_factor_enabled"
AUDIT_TWO_FACTOR_DISABLED = "two_factor_disabled"
AUDIT_ACCOUNT_APPROVED = "account_approved"
AUDIT_ACCOUNT_REJECTED = "account_rejected"
AUDIT_ROLE_CHANGED = "role_changed"
AUDIT_ACCOUNT_DEACTIVATED = "account_deactivated"
AUDIT_ACCOUNT_REACTIVATED = "account_reactivated"
AUDIT_ACCOUNT_DELETED = "account_deleted"
AUDIT_ATTENDANCE_CLEARED = "attendance_cleared"
AUDIT_ATTENDANCE_MANUAL_ENTRY = "attendance_manual_entry"
AUDIT_AUDIT_LOG_CLEARED = "audit_log_cleared"
AUDIT_ALERT_ACKNOWLEDGED = "alert_acknowledged"

ALL_AUDIT_EVENT_TYPES = (
    AUDIT_LOGIN_SUCCESS,
    AUDIT_LOGIN_FAILURE,
    AUDIT_LOGOUT,
    AUDIT_PASSWORD_CHANGE,
    AUDIT_TWO_FACTOR_ENABLED,
    AUDIT_TWO_FACTOR_DISABLED,
    AUDIT_ACCOUNT_APPROVED,
    AUDIT_ACCOUNT_REJECTED,
    AUDIT_ROLE_CHANGED,
    AUDIT_ACCOUNT_DEACTIVATED,
    AUDIT_ACCOUNT_REACTIVATED,
    AUDIT_ACCOUNT_DELETED,
    AUDIT_ATTENDANCE_CLEARED,
    AUDIT_ATTENDANCE_MANUAL_ENTRY,
    AUDIT_AUDIT_LOG_CLEARED,
    AUDIT_ALERT_ACKNOWLEDGED,
)


def _normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()[:255]


def _sanitize_text(value: str | None, max_length: int) -> str | None:
    cleaned = (value or "").strip()
    return cleaned[:max_length] if cleaned else None


def record_audit_event(
    db: Session,
    *,
    operator_email: str,
    event_type: str,
    ip_address: str | None,
    detail: str | None = None,
    commit: bool = False,
) -> AuditLog:
    entry = AuditLog(
        timestamp=datetime.utcnow(),
        operator_email=_normalize_email(operator_email) or "unknown",
        event_type=_sanitize_text(event_type, 64) or "unknown_event",
        ip_address=_sanitize_text(ip_address, 64),
        detail=_sanitize_text(detail, 2000),
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    return entry
