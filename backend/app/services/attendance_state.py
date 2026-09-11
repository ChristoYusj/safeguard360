"""
Who is on site, computed once.

Three different answers to this question used to exist: the gate service
scanned the whole attendance table, the assistant ran its own grouped query,
and the Attendance page derived it in the browser from the most recent page of
records. A worker whose entry fell outside that page was on site according to
two of them and off site according to the third, and the Check-In/Check-Out
locks are driven by the answer.

This module is the single owner. Everything else asks it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Attendance, Person


@dataclass(frozen=True)
class OnSiteWorker:
    person_id: str
    name: Optional[str]
    employee_id: Optional[str]
    shift_id: Optional[str]
    entered_at: Optional[datetime]
    attendance_id: str

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "person_id": self.person_id,
            "name": self.name,
            "employee_id": self.employee_id,
            "shift_id": self.shift_id,
            "entered_at": self.entered_at.isoformat() if self.entered_at else None,
            "attendance_id": self.attendance_id,
        }


def get_on_site_workers(db: Session) -> List[OnSiteWorker]:
    """Workers whose most recent attendance record is a granted ENTRY.

    A granted ENTRY puts someone on site; anything later for that person (an
    EXIT, or a denied ENTRY) takes them off it. Ties on the timestamp are
    broken by the record id so the answer is stable rather than dependent on
    row order.
    """
    latest = (
        db.query(
            Attendance.person_id.label("person_id"),
            func.max(Attendance.timestamp).label("latest_ts"),
        )
        .filter(Attendance.person_id.isnot(None))
        .group_by(Attendance.person_id)
        .subquery()
    )
    rows = (
        db.query(Attendance, Person)
        .join(
            latest,
            (Attendance.person_id == latest.c.person_id)
            & (Attendance.timestamp == latest.c.latest_ts),
        )
        .outerjoin(Person, Person.id == Attendance.person_id)
        .order_by(Attendance.timestamp.desc(), Attendance.id.desc())
        .all()
    )

    on_site: List[OnSiteWorker] = []
    seen: set[str] = set()
    for record, person in rows:
        if record.person_id in seen:
            continue  # two records share the latest timestamp; the first wins
        seen.add(record.person_id)
        if not record.access_granted or record.direction != "ENTRY":
            continue
        on_site.append(
            OnSiteWorker(
                person_id=record.person_id,
                name=(person.name if person else None) or record.person_name,
                employee_id=person.employee_id if person else None,
                shift_id=person.shift_id if person else None,
                entered_at=record.timestamp,
                attendance_id=record.id,
            )
        )
    return on_site


def get_on_site_person_ids(db: Session) -> set[str]:
    return {worker.person_id for worker in get_on_site_workers(db)}
