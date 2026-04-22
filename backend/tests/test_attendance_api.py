from __future__ import annotations

from app.api.attendance import clear_attendance_logs
from app.db.models import Alert, Attendance, GateReview, Person, Event
from app.services.gate_compliance import create_alert_record, create_event_record


def test_clear_attendance_logs_removes_attendance_reviews_and_ppe_history(db_session):
    person = Person(name="Alice Worker", employee_id="A-01")
    db_session.add(person)
    db_session.commit()
    db_session.refresh(person)

    attendance = Attendance(
        person_id=person.id,
        person_name=person.name,
        direction="ENTRY",
        ppe_compliant=False,
        access_granted=True,
    )
    review = GateReview(
        person_id=person.id,
        person_name=person.name,
        suggested_direction="ENTRY",
        status="PENDING",
    )
    db_session.add_all([attendance, review])
    db_session.flush()

    ppe_event = create_event_record(
        db_session,
        category="PPE",
        event_type="PPE_ENTRY_DENIED",
        severity="ALERT",
        message="Helmet missing",
    )
    create_alert_record(
        db_session,
        event=ppe_event,
        severity="ALERT",
        title="PPE Violation",
        message="Helmet missing",
    )
    create_event_record(
        db_session,
        category="DRIVER",
        event_type="fatigue_alert",
        severity="WARN",
        message="Driver fatigue",
    )
    db_session.commit()

    response = clear_attendance_logs(db_session)

    assert response.attendance_deleted == 1
    assert response.reviews_deleted == 1
    assert response.ppe_events_deleted == 1
    assert response.alerts_deleted == 1

    assert db_session.query(Attendance).count() == 0
    assert db_session.query(GateReview).count() == 0
    assert db_session.query(Alert).count() == 0
    assert db_session.query(Event).filter(Event.category == "PPE").count() == 0
    assert db_session.query(Event).filter(Event.category == "DRIVER").count() == 1
