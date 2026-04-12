"""
Alerts API.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.db.models import Alert, Event

router = APIRouter()


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
    include_inactive: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    records = (
        db.query(Alert, Event)
        .outerjoin(Event, Alert.event_id == Event.id)
        .order_by(Alert.created_at.desc())
    )
    if not include_inactive:
        records = records.filter(Alert.is_active.is_(True))
    return [_serialize_alert(alert, event) for alert, event in records.limit(limit).all()]


@router.post("/{alert_id}/ack", response_model=AlertResponse)
def acknowledge_alert(alert_id: str, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found.",
        )

    alert.is_active = False
    if alert.acknowledged_at is None:
        alert.acknowledged_at = datetime.utcnow()
    db.commit()
    db.refresh(alert)
    event = db.query(Event).filter(Event.id == alert.event_id).first() if alert.event_id else None
    return _serialize_alert(alert, event)
