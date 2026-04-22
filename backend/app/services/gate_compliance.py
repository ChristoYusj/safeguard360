"""
Gate compliance helpers shared by API and live attendance recognition.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from app.db.models import Alert, Event, GatePolicy


# Shift time windows used to flag workers arriving outside their schedule.
# Times are in local server time, 24-hour. Night wraps past midnight.
SHIFT_WINDOWS = {
    "day": (6, 14),     # 06:00 – 14:00
    "swing": (14, 22),  # 14:00 – 22:00
    "night": (22, 6),   # 22:00 – 06:00 (wraps)
}

# How long before/after the shift start the worker is considered on-schedule.
# Early arrivals and small overruns are normal — only flag clearly off-shift.
SHIFT_GRACE_HOURS = 1.5


def is_within_shift(shift_id: Optional[str], when: Optional[datetime] = None) -> bool:
    """True if `when` falls within the configured window for `shift_id`.

    Returns True if shift_id is unknown/None (we don't penalise unassigned
    workers). Applies a grace window around the boundaries so clocking in
    a bit early or running late doesn't create false warnings.
    """
    if not shift_id:
        return True
    window = SHIFT_WINDOWS.get(shift_id.lower())
    if not window:
        return True
    start_h, end_h = window
    t = (when or datetime.now()).time()
    hour = t.hour + t.minute / 60.0

    # Expand window by grace on both sides.
    start_h_expanded = (start_h - SHIFT_GRACE_HOURS) % 24
    end_h_expanded = (end_h + SHIFT_GRACE_HOURS) % 24

    if start_h < end_h:
        # Normal window (day/swing). Handle potential underflow on start.
        if start_h_expanded < end_h_expanded:
            return start_h_expanded <= hour <= end_h_expanded
        # Grace pushed start past midnight.
        return hour >= start_h_expanded or hour <= end_h_expanded
    # Wrapping window (night).
    return hour >= start_h_expanded or hour <= end_h_expanded

DEFAULT_GATE_POLICY = {
    "require_helmet": True,
    "require_vest": True,
    "deny_non_compliant_entry": True,
    "manual_override_enabled": True,
    "enforce_stage": "ENTRY_ONLY",
}

DEFAULT_PPE_DETAILS = {
    "status": "not_evaluated",
    "required_items": [],
    "detected_items": [],
    "missing_items": [],
    "detector_confidences": {},
    "override_used": False,
    "override_reason_type": None,
    "detector_available": False,
    "detector_message": None,
}


def _parse_json_text(raw_value: Any, fallback: Any) -> Any:
    if raw_value in (None, "", b""):
        return deepcopy(fallback)
    if isinstance(raw_value, (dict, list)):
        return deepcopy(raw_value)
    try:
        parsed = json.loads(raw_value)
    except Exception:
        return deepcopy(fallback)
    return parsed if parsed is not None else deepcopy(fallback)


def normalize_review_reasons(raw_value: Any) -> List[str]:
    parsed = _parse_json_text(raw_value, [])
    if not isinstance(parsed, list):
        return []
    normalized: List[str] = []
    for item in parsed:
        if not item:
            continue
        reason = str(item).strip()
        if reason and reason not in normalized:
            normalized.append(reason)
    return normalized


def serialize_review_reasons(reasons: Optional[Iterable[str]]) -> str:
    return json.dumps(normalize_review_reasons(list(reasons or [])))


def normalize_ppe_details(raw_value: Any) -> Dict[str, Any]:
    parsed = _parse_json_text(raw_value, DEFAULT_PPE_DETAILS)
    if not isinstance(parsed, dict):
        parsed = {}

    details = {**DEFAULT_PPE_DETAILS, **parsed}
    details["required_items"] = [
        str(item).strip()
        for item in details.get("required_items") or []
        if str(item).strip()
    ]
    details["detected_items"] = [
        str(item).strip()
        for item in details.get("detected_items") or []
        if str(item).strip()
    ]
    details["missing_items"] = [
        str(item).strip()
        for item in details.get("missing_items") or []
        if str(item).strip()
    ]
    confidence_map = details.get("detector_confidences") or {}
    if not isinstance(confidence_map, dict):
        confidence_map = {}
    details["detector_confidences"] = {
        str(key): float(value)
        for key, value in confidence_map.items()
        if value is not None
    }
    details["override_used"] = bool(details.get("override_used"))
    details["override_reason_type"] = (
        str(details["override_reason_type"]).strip()
        if details.get("override_reason_type")
        else None
    )
    details["detector_available"] = bool(details.get("detector_available"))
    details["detector_message"] = (
        str(details["detector_message"]).strip()
        if details.get("detector_message")
        else None
    )
    details["status"] = str(details.get("status") or "not_evaluated").strip()
    return details


def serialize_ppe_details(details: Optional[Dict[str, Any]]) -> str:
    return json.dumps(normalize_ppe_details(details or {}))


def get_or_create_gate_policy(db: Session) -> GatePolicy:
    policy = db.query(GatePolicy).order_by(GatePolicy.created_at.asc()).first()
    if policy:
        return policy

    policy = GatePolicy(**DEFAULT_GATE_POLICY)
    db.add(policy)
    db.flush()
    return policy


def serialize_gate_policy(policy: GatePolicy) -> Dict[str, Any]:
    return {
        "id": policy.id,
        "require_helmet": bool(policy.require_helmet),
        "require_vest": bool(policy.require_vest),
        "deny_non_compliant_entry": bool(policy.deny_non_compliant_entry),
        "manual_override_enabled": bool(policy.manual_override_enabled),
        "enforce_stage": policy.enforce_stage or DEFAULT_GATE_POLICY["enforce_stage"],
        "created_at": policy.created_at.isoformat() if policy.created_at else None,
        "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
    }


def get_required_ppe_items(policy: GatePolicy) -> List[str]:
    required_items: List[str] = []
    if policy.require_helmet:
        required_items.append("helmet")
    if policy.require_vest:
        required_items.append("vest")
    return required_items


def ppe_reason_messages(review_reasons: Iterable[str]) -> List[str]:
    messages: List[str] = []
    for reason in normalize_review_reasons(review_reasons):
        if reason == "face_confidence":
            messages.append("Face confidence needs operator review.")
        elif reason == "uncertain_ppe":
            messages.append("PPE status is uncertain.")
        elif reason.startswith("missing_"):
            messages.append(f"Missing {reason.replace('missing_', '').replace('_', ' ')}.")
        elif reason.startswith("off_shift_"):
            shift_name = reason.replace("off_shift_", "").replace("_", " ")
            messages.append(
                f"Arriving outside {shift_name} shift window."
            )
    return messages


def create_event_record(
    db: Session,
    *,
    category: str,
    event_type: str,
    severity: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    snapshot_path: Optional[str] = None,
    is_resolved: bool = False,
) -> Event:
    event = Event(
        category=category,
        event_type=event_type,
        severity=severity,
        data=json.dumps(data or {}),
        snapshot_path=snapshot_path,
        is_resolved=is_resolved,
    )
    db.add(event)
    db.flush()
    return event


def create_alert_record(
    db: Session,
    *,
    event: Event,
    severity: str,
    title: str,
    message: str,
    is_active: bool = True,
) -> Alert:
    alert = Alert(
        event_id=event.id,
        severity=severity,
        title=title,
        message=message,
        is_active=is_active,
    )
    db.add(alert)
    db.flush()
    return alert
