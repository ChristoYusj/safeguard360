"""
Event log API.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api._admin_helpers import get_request_role
from app.db.connection import get_db
from app.db.models import Event
from app.services.rbac import DRIVER_EVENT_CATEGORIES, visible_event_domains

router = APIRouter()


def scope_events_to_role(query, role: str | None):
    """Restrict an Event query to the domains the role may see.

    Gate-side events are everything that is not a driver category (today:
    "PPE"); driver-side events are DRIVER_EVENT_CATEGORIES.
    """
    domains = visible_event_domains(role)
    if "gate" in domains and "driver" in domains:
        return query
    if "driver" in domains:
        return query.filter(Event.category.in_(DRIVER_EVENT_CATEGORIES))
    if "gate" in domains:
        return query.filter(Event.category.notin_(DRIVER_EVENT_CATEGORIES))
    return query.filter(False)


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
    request: Request,
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = scope_events_to_role(
        db.query(Event).order_by(Event.timestamp.desc()), get_request_role(request)
    )
    if category:
        query = query.filter(Event.category == category.upper())
    return [_serialize_event(event) for event in query.limit(limit).all()]
