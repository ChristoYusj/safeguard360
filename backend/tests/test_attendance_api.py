"""DELETE /api/attendance/logs clears attendance, reviews and PPE history only.

Exercised over HTTP as the admin (the route is admin-only since Phase 1a).
"""
from __future__ import annotations

from app.db.connection import SessionLocal
from app.db.models import Alert, Attendance, Event, GateReview, Person
from app.services.gate_compliance import create_alert_record, create_event_record
from tests.helpers import login_admin


def _seed_history() -> None:
    db = SessionLocal()
    try:
        person = Person(name="Alice Worker", employee_id="A-01")
        db.add(person)
        db.commit()
        db.refresh(person)

        db.add_all(
            [
                Attendance(
                    person_id=person.id,
                    person_name=person.name,
                    direction="ENTRY",
                    ppe_compliant=False,
                    access_granted=True,
                ),
                GateReview(
                    person_id=person.id,
                    person_name=person.name,
                    suggested_direction="ENTRY",
                    status="PENDING",
                ),
            ]
        )
        db.flush()

        ppe_event = create_event_record(
            db,
            category="PPE",
            event_type="PPE_ENTRY_DENIED",
            severity="ALERT",
            message="Helmet missing",
        )
        create_alert_record(
            db,
            event=ppe_event,
            severity="ALERT",
            title="PPE Violation",
            message="Helmet missing",
        )
        create_event_record(
            db,
            category="DRIVER",
            event_type="fatigue_alert",
            severity="WARN",
            message="Driver fatigue",
        )
        db.commit()
    finally:
        db.close()


def _count(model, *criteria) -> int:
    db = SessionLocal()
    try:
        query = db.query(model)
        for criterion in criteria:
            query = query.filter(criterion)
        return query.count()
    finally:
        db.close()


def test_clear_attendance_logs_removes_attendance_reviews_and_ppe_history(client):
    login_admin(client)
    _seed_history()

    response = client.delete("/api/attendance/logs")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["attendance_deleted"] == 1
    assert body["reviews_deleted"] == 1
    assert body["ppe_events_deleted"] == 1
    assert body["alerts_deleted"] == 1

    assert _count(Attendance) == 0
    assert _count(GateReview) == 0
    assert _count(Alert) == 0
    assert _count(Event, Event.category == "PPE") == 0
    assert _count(Event, Event.category == "DRIVER") == 1
