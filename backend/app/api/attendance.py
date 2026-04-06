"""
Attendance log API.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.db.models import Attendance, GateReview, Person
from app.services.persons import (
    parse_image_data_url,
    read_image_data_url,
    write_attendance_snapshot,
)

router = APIRouter()


class AttendanceCreateRequest(BaseModel):
    person_id: Optional[str] = None
    person_name: Optional[str] = Field(default=None, max_length=100)
    direction: Literal["ENTRY", "EXIT"] = "ENTRY"
    ppe_compliant: bool = True
    access_granted: bool = True
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    snapshot_data_url: Optional[str] = None


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
    confidence: Optional[float] = None


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


class GateReviewDecisionRequest(BaseModel):
    decision: Literal["APPROVED", "DENIED"]
    decided_by: Optional[str] = Field(default=None, max_length=100)
    note: Optional[str] = Field(default=None, max_length=500)


class GateDirectionModeRequest(BaseModel):
    direction_mode: Literal["ENTRY", "EXIT"]


class GateDirectionModeResponse(BaseModel):
    direction_mode: Literal["ENTRY", "EXIT"]
    candidate_scope: str


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
        confidence=record.confidence,
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
) -> Attendance:
    record = Attendance(
        person_id=person.id if person else None,
        person_name=person_name,
        direction=direction,
        ppe_compliant=ppe_compliant,
        access_granted=access_granted,
        confidence=confidence,
    )
    db.add(record)
    db.flush()

    if snapshot_data_url:
        image_bytes, mime_type = parse_image_data_url(snapshot_data_url)
        record.snapshot_path = write_attendance_snapshot(record.id, image_bytes, mime_type)
    elif snapshot_path:
        record.snapshot_path = snapshot_path

    return record


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
    db: Session = Depends(get_db),
):
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
        confidence=payload.confidence,
        snapshot_data_url=payload.snapshot_data_url,
    )

    db.commit()
    db.refresh(record)
    try:
        from app.services.gate_attendance import gate_attendance_recognizer

        gate_attendance_recognizer.invalidate_cache()
    except Exception:
        pass
    return _serialize_attendance(record)


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
    db: Session = Depends(get_db),
):
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
    review.decided_at = datetime.utcnow()
    review.decided_by = payload.decided_by.strip() if payload.decided_by else "Authorized operator"
    review.decision_note = payload.note.strip() if payload.note else None

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
        _create_attendance_record(
            db,
            person=person,
            person_name=review.person_name or (person.name if person else "Unknown worker"),
            direction=review.suggested_direction or "ENTRY",
            ppe_compliant=True,
            access_granted=True,
            confidence=review.confidence,
            snapshot_path=review.snapshot_path,
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
