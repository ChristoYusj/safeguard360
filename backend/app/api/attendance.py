"""
Attendance log API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api._admin_helpers import get_admin_user
from app.db.connection import get_db
from app.db.models import Alert, Attendance, Event, GateReview, Person, User
from app.services.audit import (
    AUDIT_ATTENDANCE_CLEARED,
    AUDIT_ATTENDANCE_MANUAL_ENTRY,
    record_audit_event,
)
from app.services.auth import get_client_ip
from app.services.persons import (
    parse_image_data_url,
    read_image_data_url,
    write_attendance_snapshot,
)
from app.services.gate_compliance import (
    create_event_record,
    get_or_create_gate_policy,
    normalize_ppe_details,
    normalize_review_reasons,
    ppe_reason_messages,
    serialize_gate_policy,
    serialize_ppe_details,
)

router = APIRouter()


class AttendanceCreateRequest(BaseModel):
    person_id: Optional[str] = None
    person_name: Optional[str] = Field(default=None, max_length=100)
    direction: Literal["ENTRY", "EXIT"] = "ENTRY"
    ppe_compliant: bool = True
    access_granted: bool = True
    # ~7.5 MB of base64; the whole body is buffered before decoding.
    snapshot_data_url: Optional[str] = Field(default=None, max_length=10_000_000)
    ppe_details: Optional[Dict[str, Any]] = None
    camera_source_type: Optional[str] = None
    camera_source_id: Optional[str] = None
    # `confidence` and `log_method` are deliberately not accepted: a manual
    # entry is always log_method="MANUAL" with no recogniser confidence, so it
    # can never be made to look like a face-recognition scan.


class AttendanceResponse(BaseModel):
    id: str
    person_id: Optional[str] = None
    person_name: Optional[str] = None
    person_employee_id: Optional[str] = None
    direction: str
    timestamp: Optional[str] = None
    ppe_compliant: bool
    access_granted: bool
    snapshot_path: Optional[str] = None
    snapshot_data_url: Optional[str] = None
    confidence: Optional[float] = None
    ppe_details: Dict[str, Any] = Field(default_factory=dict)
    camera_source_type: Optional[str] = None
    camera_source_id: Optional[str] = None
    log_method: Optional[str] = None


class GateReviewResponse(BaseModel):
    id: str
    person_id: Optional[str] = None
    person_name: Optional[str] = None
    person_employee_id: Optional[str] = None
    suggested_direction: Optional[str] = None
    confidence: Optional[float] = None
    timestamp: Optional[str] = None
    status: str
    decision_note: Optional[str] = None
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None
    snapshot_path: Optional[str] = None
    snapshot_data_url: Optional[str] = None
    review_reasons: List[str] = Field(default_factory=list)
    ppe_details: Dict[str, Any] = Field(default_factory=dict)


class GateReviewDecisionRequest(BaseModel):
    decision: Literal["APPROVED", "DENIED"]
    # Attribution comes from the authenticated session, never from the body.
    note: Optional[str] = Field(default=None, max_length=500)


def _require_operator(request: Request) -> User:
    """The authenticated operator the middleware attached to the request."""
    current_user = getattr(request.state, "user", None)
    if not isinstance(current_user, User):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return current_user


class GateDirectionModeRequest(BaseModel):
    direction_mode: Literal["ENTRY", "EXIT"]


class GateDirectionModeResponse(BaseModel):
    direction_mode: Literal["ENTRY", "EXIT"]
    candidate_scope: str


class PpePolicyResponse(BaseModel):
    id: str
    require_helmet: bool
    require_vest: bool
    deny_non_compliant_entry: bool
    manual_override_enabled: bool
    enforce_stage: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PpePolicyUpdateRequest(BaseModel):
    require_helmet: Optional[bool] = None
    require_vest: Optional[bool] = None
    deny_non_compliant_entry: Optional[bool] = None


class AttendanceLogClearResponse(BaseModel):
    attendance_deleted: int
    reviews_deleted: int
    ppe_events_deleted: int
    alerts_deleted: int


def _serialize_attendance(record: Attendance) -> AttendanceResponse:
    return AttendanceResponse(
        id=record.id,
        person_id=record.person_id,
        person_name=record.person_name,
        person_employee_id=record.person.employee_id if record.person else None,
        direction=record.direction,
        timestamp=record.timestamp.isoformat() if record.timestamp else None,
        ppe_compliant=record.ppe_compliant,
        access_granted=record.access_granted,
        snapshot_path=record.snapshot_path,
        snapshot_data_url=read_image_data_url(record.snapshot_path),
        confidence=record.confidence,
        ppe_details=normalize_ppe_details(record.ppe_details),
        camera_source_type=record.camera_source_type,
        camera_source_id=record.camera_source_id,
        log_method=record.log_method,
    )


def _serialize_gate_review(review: GateReview) -> GateReviewResponse:
    return GateReviewResponse(
        id=review.id,
        person_id=review.person_id,
        person_name=review.person_name,
        person_employee_id=review.person.employee_id if review.person else None,
        suggested_direction=review.suggested_direction,
        confidence=review.confidence,
        timestamp=review.timestamp.isoformat() if review.timestamp else None,
        status=review.status,
        decision_note=review.decision_note,
        decided_at=review.decided_at.isoformat() if review.decided_at else None,
        decided_by=review.decided_by,
        snapshot_path=review.snapshot_path,
        snapshot_data_url=read_image_data_url(review.snapshot_path),
        review_reasons=normalize_review_reasons(review.review_reasons),
        ppe_details=normalize_ppe_details(review.ppe_details),
    )


def _create_attendance_record(
    db: Session,
    *,
    person: Optional[Person],
    person_name: str,
    direction: str,
    ppe_compliant: bool,
    access_granted: bool,
    confidence: Optional[float],
    snapshot_data_url: Optional[str] = None,
    snapshot_path: Optional[str] = None,
    ppe_details: Optional[Dict[str, Any]] = None,
    camera_source_type: Optional[str] = None,
    camera_source_id: Optional[str] = None,
    log_method: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> Attendance:
    record = Attendance(
        person_id=person.id if person else None,
        person_name=person_name,
        direction=direction,
        timestamp=timestamp or datetime.now(),
        ppe_compliant=ppe_compliant,
        access_granted=access_granted,
        confidence=confidence,
        ppe_details=serialize_ppe_details(ppe_details),
        camera_source_type=camera_source_type,
        camera_source_id=camera_source_id,
        log_method=log_method or "MANUAL",
    )
    db.add(record)
    db.flush()

    if snapshot_data_url:
        try:
            image_bytes, mime_type = parse_image_data_url(snapshot_data_url)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        record.snapshot_path = write_attendance_snapshot(record.id, image_bytes, mime_type)
    elif snapshot_path:
        record.snapshot_path = snapshot_path

    return record


def _get_live_camera_source() -> Dict[str, Optional[str]]:
    try:
        from app.camera.manager import camera_manager

        if not camera_manager.running:
            return {"camera_source_type": None, "camera_source_id": None}

        return {
            "camera_source_type": camera_manager.source_type or None,
            "camera_source_id": camera_manager.source_id or None,
        }
    except Exception:
        return {"camera_source_type": None, "camera_source_id": None}


def _resolve_override_reason_type(review_reasons: List[str]) -> Optional[str]:
    has_face_reason = "face_confidence" in review_reasons
    has_ppe_reason = any(
        reason == "uncertain_ppe" or reason.startswith("missing_")
        for reason in review_reasons
    )
    if has_face_reason and has_ppe_reason:
        return "combined"
    if has_ppe_reason:
        return "ppe_non_compliance"
    if has_face_reason:
        return "face_confidence"
    return None


def _is_ppe_compliant_after_review(review_reasons: List[str], ppe_details: Dict[str, Any]) -> bool:
    if any(
        reason == "uncertain_ppe" or reason.startswith("missing_")
        for reason in review_reasons
    ):
        return False
    return ppe_details.get("status") in {
        "compliant",
        "skipped",
        "not_evaluated",
    }


@router.get("", response_model=List[AttendanceResponse])
def list_attendance(
    limit: int = Query(default=50, ge=1, le=500),
    person_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Attendance).order_by(Attendance.timestamp.desc())
    if person_id:
        query = query.filter(Attendance.person_id == person_id)
    records = query.limit(limit).all()
    return [_serialize_attendance(record) for record in records]


@router.post("", response_model=AttendanceResponse, status_code=status.HTTP_201_CREATED)
def create_attendance_record(
    payload: AttendanceCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    operator = _require_operator(request)
    person = None
    if payload.person_id:
        person = db.query(Person).filter(Person.id == payload.person_id).first()
        if not person:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found.")

    resolved_name = payload.person_name.strip() if payload.person_name else None
    if person and not resolved_name:
        resolved_name = person.name

    if not person and not resolved_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Attendance requires either person_id or person_name.",
        )

    record = _create_attendance_record(
        db,
        person=person,
        person_name=resolved_name,
        direction=payload.direction,
        ppe_compliant=payload.ppe_compliant,
        access_granted=payload.access_granted,
        confidence=None,
        snapshot_data_url=payload.snapshot_data_url,
        ppe_details=payload.ppe_details,
        camera_source_type=payload.camera_source_type,
        camera_source_id=payload.camera_source_id,
        log_method="MANUAL",
    )
    db.flush()
    record_audit_event(
        db,
        operator_email=operator.email,
        event_type=AUDIT_ATTENDANCE_MANUAL_ENTRY,
        ip_address=get_client_ip(request),
        detail=(
            f"Manual {payload.direction} recorded for {resolved_name} "
            f"(attendance {record.id}, access_granted={payload.access_granted})."
        ),
    )

    db.commit()
    db.refresh(record)
    try:
        from app.services.gate_attendance import gate_attendance_recognizer

        gate_attendance_recognizer.invalidate_cache()
    except Exception:
        pass
    return _serialize_attendance(record)


@router.delete("/logs", response_model=AttendanceLogClearResponse)
def clear_attendance_logs(request: Request, db: Session = Depends(get_db)):
    # Destroys the attendance history, every pending review and all PPE
    # alerts: admin only, and the wipe itself is written to the audit log.
    admin_user = get_admin_user(request, db)
    ppe_event_ids = [
        event_id
        for (event_id,) in db.query(Event.id).filter(Event.category == "PPE").all()
    ]

    attendance_deleted = db.query(Attendance).delete(synchronize_session=False)
    reviews_deleted = db.query(GateReview).delete(synchronize_session=False)
    alerts_deleted = 0
    if ppe_event_ids:
        alerts_deleted = (
            db.query(Alert)
            .filter(Alert.event_id.in_(ppe_event_ids))
            .delete(synchronize_session=False)
        )
    ppe_events_deleted = (
        db.query(Event)
        .filter(Event.category == "PPE")
        .delete(synchronize_session=False)
    )
    record_audit_event(
        db,
        operator_email=admin_user.email,
        event_type=AUDIT_ATTENDANCE_CLEARED,
        ip_address=get_client_ip(request),
        detail=(
            f"Cleared {attendance_deleted} attendance records, {reviews_deleted} gate "
            f"reviews, {ppe_events_deleted} PPE events and {alerts_deleted} alerts."
        ),
    )

    db.commit()
    try:
        from app.services.gate_attendance import gate_attendance_recognizer

        gate_attendance_recognizer.invalidate_cache()
    except Exception:
        pass

    return AttendanceLogClearResponse(
        attendance_deleted=attendance_deleted,
        reviews_deleted=reviews_deleted,
        ppe_events_deleted=ppe_events_deleted,
        alerts_deleted=alerts_deleted,
    )


@router.get("/ppe-policy", response_model=PpePolicyResponse)
def get_ppe_policy(db: Session = Depends(get_db)):
    policy = get_or_create_gate_policy(db)
    db.commit()
    db.refresh(policy)
    return PpePolicyResponse(**serialize_gate_policy(policy))


@router.put("/ppe-policy", response_model=PpePolicyResponse)
def update_ppe_policy(
    payload: PpePolicyUpdateRequest,
    db: Session = Depends(get_db),
):
    policy = get_or_create_gate_policy(db)

    if payload.require_helmet is not None:
        policy.require_helmet = payload.require_helmet
    if payload.require_vest is not None:
        policy.require_vest = payload.require_vest
    if payload.deny_non_compliant_entry is not None:
        policy.deny_non_compliant_entry = payload.deny_non_compliant_entry

    db.commit()
    db.refresh(policy)
    try:
        from app.services.gate_attendance import gate_attendance_recognizer

        gate_attendance_recognizer.invalidate_cache()
    except Exception:
        pass
    return PpePolicyResponse(**serialize_gate_policy(policy))


@router.get("/reviews", response_model=List[GateReviewResponse])
def list_gate_reviews(
    status_filter: Literal["pending", "resolved", "all"] = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(GateReview).order_by(GateReview.timestamp.desc())
    if status_filter == "pending":
        query = query.filter(GateReview.status == "PENDING")
    elif status_filter == "resolved":
        query = query.filter(GateReview.status.in_(["APPROVED", "DENIED"]))
    records = query.limit(limit).all()
    return [_serialize_gate_review(record) for record in records]


@router.post("/reviews/{review_id}/decision", response_model=GateReviewResponse)
def decide_gate_review(
    review_id: str,
    payload: GateReviewDecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    operator = _require_operator(request)
    review = db.query(GateReview).filter(GateReview.id == review_id).first()
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gate review not found.",
        )

    if review.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This gate review has already been resolved.",
        )

    review.status = payload.decision
    review.decided_at = datetime.now()
    review.decided_by = operator.email
    review.decision_note = payload.note.strip() if payload.note else None
    review_reasons = normalize_review_reasons(review.review_reasons)
    ppe_details = normalize_ppe_details(review.ppe_details)
    override_reason_type = _resolve_override_reason_type(review_reasons)

    if payload.decision == "APPROVED":
        ppe_details["override_used"] = True
        ppe_details["override_reason_type"] = override_reason_type
    elif override_reason_type:
        ppe_details["override_reason_type"] = override_reason_type
    review.ppe_details = serialize_ppe_details(ppe_details)

    try:
        from app.services.gate_attendance import gate_attendance_recognizer

        gate_attendance_recognizer.resolve_review(
            review.person_id,
            approved=payload.decision == "APPROVED",
        )
    except Exception:
        pass

    if payload.decision == "APPROVED":
        person = db.query(Person).filter(Person.id == review.person_id).first() if review.person_id else None
        camera_source = _get_live_camera_source()
        _create_attendance_record(
            db,
            person=person,
            person_name=review.person_name or (person.name if person else "Unknown worker"),
            direction=review.suggested_direction or "ENTRY",
            ppe_compliant=_is_ppe_compliant_after_review(review_reasons, ppe_details),
            access_granted=True,
            confidence=review.confidence,
            snapshot_path=review.snapshot_path,
            ppe_details=ppe_details,
            camera_source_type=camera_source["camera_source_type"],
            camera_source_id=camera_source["camera_source_id"],
            log_method="MANUAL",
            timestamp=review.decided_at,
        )
        if override_reason_type in {"ppe_non_compliance", "combined"}:
            create_event_record(
                db,
                category="PPE",
                event_type="PPE_OVERRIDE_GRANTED",
                severity="WARNING",
                message=(
                    f"{review.person_name or 'Worker'} was granted entry after PPE override."
                ),
                data={
                    "person_id": review.person_id,
                    "person_name": review.person_name,
                    "direction": review.suggested_direction,
                    "review_id": review.id,
                    "review_reasons": review_reasons,
                    "ppe_details": ppe_details,
                    "decided_by": review.decided_by,
                },
                snapshot_path=review.snapshot_path,
                is_resolved=True,
            )
    elif override_reason_type in {"ppe_non_compliance", "combined"}:
        create_event_record(
            db,
            category="PPE",
            event_type="PPE_ENTRY_DENIED",
            severity="ALERT",
            message=(
                f"{review.person_name or 'Worker'} was denied entry after PPE review."
            ),
            data={
                "person_id": review.person_id,
                "person_name": review.person_name,
                "direction": review.suggested_direction,
                "review_id": review.id,
                "review_reasons": review_reasons,
                "ppe_details": ppe_details,
                "decided_by": review.decided_by,
                "decision_note": review.decision_note,
                "reason_messages": ppe_reason_messages(review_reasons),
            },
            snapshot_path=review.snapshot_path,
            is_resolved=True,
        )

    db.commit()
    db.refresh(review)
    try:
        from app.services.gate_attendance import gate_attendance_recognizer

        gate_attendance_recognizer.invalidate_cache()
    except Exception:
        pass
    return _serialize_gate_review(review)


@router.get("/gate-mode", response_model=GateDirectionModeResponse)
def get_gate_direction_mode():
    from app.services.gate_attendance import gate_attendance_recognizer

    direction_mode = gate_attendance_recognizer.get_gate_direction_mode()
    return GateDirectionModeResponse(
        direction_mode=direction_mode,
        candidate_scope="checked_in_only" if direction_mode == "EXIT" else "all_enrolled",
    )


@router.post("/gate-mode", response_model=GateDirectionModeResponse)
def set_gate_direction_mode(payload: GateDirectionModeRequest):
    from app.services.gate_attendance import gate_attendance_recognizer

    try:
        direction_mode = gate_attendance_recognizer.set_gate_direction_mode(payload.direction_mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return GateDirectionModeResponse(
        direction_mode=direction_mode,
        candidate_scope="checked_in_only" if direction_mode == "EXIT" else "all_enrolled",
    )
