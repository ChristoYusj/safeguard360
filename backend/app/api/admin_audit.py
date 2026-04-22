"""
Admin-only audit log routes.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.db.models import AuditLog, User
from app.services.audit import ALL_AUDIT_EVENT_TYPES
from app.services.rbac import ADMIN_ROLE


router = APIRouter()


def _get_admin_user(request: Request, db: Session) -> User:
    current_user = getattr(request.state, "user", None)
    if not isinstance(current_user, User):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    admin_user = db.query(User).filter(User.id == current_user.id).first()
    if not admin_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    if admin_user.role != ADMIN_ROLE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    return admin_user


@router.get("/audit-logs")
def list_audit_logs(
    request: Request,
    event_type: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    _get_admin_user(request, db)

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
    _get_admin_user(request, db)
    deleted_count = db.query(AuditLog).delete()
    db.commit()
    return {
        "success": True,
        "deleted_count": deleted_count,
    }
