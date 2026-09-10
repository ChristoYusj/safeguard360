"""
Alerts API.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api._admin_helpers import get_request_role
from app.db.connection import get_db
from app.db.models import Alert, Event, User
from app.services.audit import AUDIT_ALERT_ACKNOWLEDGED, record_audit_event
from app.services.auth import get_client_ip
from app.services.rbac import (
    DRIVER_EVENT_CATEGORIES,
    event_category_domain,
    role_can_see_domain,
    visible_event_domains,
)

router = APIRouter()


def _scope_alerts_to_role(query, role: str | None):
    """Alerts inherit the domain of their event; an alert with no event is
    treated as gate-side, like every event category that is not DRIVER."""
    domains = visible_event_domains(role)
    if "gate" in domains and "driver" in domains:
        return query
    if "driver" in domains:
        return query.filter(Event.category.in_(DRIVER_EVENT_CATEGORIES))
    if "gate" in domains:
        return query.filter(
            or_(Event.category.is_(None), Event.category.notin_(DRIVER_EVENT_CATEGORIES))
        )
    return query.filter(False)


class AlertResponse(BaseModel):
    id: str
    event_id: Optional[str] = None
    severity: str
    title: str
    message: Optional[str] = None
    created_at: Optional[str] = None
    is_active: bool
    acknowledged_at: Optional[str] = None
    category: Optional[str] = None
    event_type: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    snapshot_path: Optional[str] = None


def _serialize_alert(alert: Alert, event: Optional[Event]) -> AlertResponse:
    payload = {}
    if event and event.data:
        try:
            payload = json.loads(event.data)
        except Exception:
            payload = {}

    return AlertResponse(
        id=alert.id,
        event_id=alert.event_id,
        severity=alert.severity,
        title=alert.title,
        message=alert.message,
        created_at=alert.created_at.isoformat() if alert.created_at else None,
        is_active=bool(alert.is_active),
        acknowledged_at=alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        category=event.category if event else None,
        event_type=event.event_type if event else None,
        data=payload if isinstance(payload, dict) else {},
        snapshot_path=event.snapshot_path if event else None,
    )


@router.get("", response_model=List[AlertResponse])
def list_alerts(
    request: Request,
    include_inactive: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    records = _scope_alerts_to_role(
        db.query(Alert, Event)
        .outerjoin(Event, Alert.event_id == Event.id)
        .order_by(Alert.created_at.desc()),
        get_request_role(request),
    )
    if not include_inactive:
        records = records.filter(Alert.is_active.is_(True))
    return [_serialize_alert(alert, event) for alert, event in records.limit(limit).all()]


@router.post("/{alert_id}/ack", response_model=AlertResponse)
def acknowledge_alert(alert_id: str, request: Request, db: Session = Depends(get_db)):
    operator = getattr(request.state, "user", None)
    if not isinstance(operator, User):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found.",
        )
    event = db.query(Event).filter(Event.id == alert.event_id).first() if alert.event_id else None
    if not role_can_see_domain(operator.role, event_category_domain(event.category if event else None)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")

    alert.is_active = False
    if alert.acknowledged_at is None:
        alert.acknowledged_at = datetime.utcnow()
    # Alerts carry no actor column; the audit log records who silenced what.
    record_audit_event(
        db,
        operator_email=operator.email,
        event_type=AUDIT_ALERT_ACKNOWLEDGED,
        ip_address=get_client_ip(request),
        detail=f"Acknowledged alert {alert.id} ({alert.severity}: {alert.title}).",
    )
    db.commit()
    db.refresh(alert)
    return _serialize_alert(alert, event)
