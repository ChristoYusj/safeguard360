"""
Event log API.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.db.models import Event

router = APIRouter()


class EventResponse(BaseModel):
    id: str
    category: str
    event_type: str
    severity: str
    timestamp: Optional[str] = None
    message: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    snapshot_path: Optional[str] = None
    is_resolved: bool


def _serialize_event(event: Event) -> EventResponse:
    payload = {}
    if event.data:
        try:
            payload = json.loads(event.data)
        except Exception:
            payload = {}

    message = payload.get("message") if isinstance(payload, dict) else None
    if not message:
        message = payload.get("title") if isinstance(payload, dict) else None

    return EventResponse(
        id=event.id,
        category=event.category,
        event_type=event.event_type,
        severity=event.severity,
        timestamp=event.timestamp.isoformat() if event.timestamp else None,
        message=message,
        data=payload if isinstance(payload, dict) else {},
        snapshot_path=event.snapshot_path,
        is_resolved=bool(event.is_resolved),
    )


@router.get("", response_model=List[EventResponse])
def list_events(
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(Event).order_by(Event.timestamp.desc())
    if category:
        query = query.filter(Event.category == category.upper())
    return [_serialize_event(event) for event in query.limit(limit).all()]
