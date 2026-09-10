"""
Admin-only audit log routes.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api._admin_helpers import get_admin_user
from app.db.connection import get_db
from app.db.models import AuditLog
from app.services.audit import (
    ALL_AUDIT_EVENT_TYPES,
    AUDIT_AUDIT_LOG_CLEARED,
    record_audit_event,
)
from app.services.auth import get_client_ip


router = APIRouter()


@router.get("/audit-logs")
def list_audit_logs(
    request: Request,
    event_type: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    get_admin_user(request, db)

    query = db.query(AuditLog)

    normalized_event_type = (event_type or "").strip().lower()
    if normalized_event_type:
        query = query.filter(AuditLog.event_type == normalized_event_type)

    if date_from:
        try:
            start = datetime.fromisoformat(date_from)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="date_from must be a valid ISO date.",
            ) from exc
        query = query.filter(AuditLog.timestamp >= start)

    if date_to:
        try:
            end = datetime.fromisoformat(date_to) + timedelta(days=1)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="date_to must be a valid ISO date.",
            ) from exc
        query = query.filter(AuditLog.timestamp < end)

    entries = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()

    return {
        "event_types": list(ALL_AUDIT_EVENT_TYPES),
        "logs": [
            {
                "id": entry.id,
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "operator_email": entry.operator_email,
                "event_type": entry.event_type,
                "ip_address": entry.ip_address,
                "detail": entry.detail,
            }
            for entry in entries
        ],
    }


@router.delete("/audit-logs")
def clear_audit_logs(
    request: Request,
    db: Session = Depends(get_db),
):
    admin_user = get_admin_user(request, db)
    deleted_count = db.query(AuditLog).delete()
    # Written after the delete, in the same transaction, so the wipe is the
    # first entry of the new log instead of an untraceable gap.
    record_audit_event(
        db,
        operator_email=admin_user.email,
        event_type=AUDIT_AUDIT_LOG_CLEARED,
        ip_address=get_client_ip(request),
        detail=f"Cleared {deleted_count} audit log entries.",
    )
    db.commit()
    return {
        "success": True,
        "deleted_count": deleted_count,
    }
