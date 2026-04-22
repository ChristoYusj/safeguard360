from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from app.db.models import Attendance, Event, Person
from app.services.gate_attendance import GateAttendanceRecognizer


def test_smooth_ppe_status_latches_detected_items_across_transient_misses():
    recognizer = GateAttendanceRecognizer()

    compliant_frame = {
        "status": "compliant",
        "required_items": ["helmet", "vest"],
        "detected_items": ["helmet", "vest"],
        "missing_items": [],
        "detector_confidences": {"helmet": 0.94, "vest": 0.91},
        "detector_available": True,
        "detector_message": "Required PPE detected.",
    }
    for index in range(3):
        details = recognizer._smooth_ppe_status(
            person_id="worker-1",
            raw_details=compliant_frame,
            now_ts=100.0 + (index * 0.2),
        )

    assert details["status"] == "compliant"
    assert set(details["latched_items"]) == {"helmet", "vest"}

    transient_miss = {
        "status": "non_compliant",
        "required_items": ["helmet", "vest"],
        "detected_items": ["vest"],
        "missing_items": ["helmet"],
        "detector_confidences": {"vest": 0.89},
        "detector_available": True,
        "detector_message": "One or more required PPE items are missing.",
    }
    held = recognizer._smooth_ppe_status(
        person_id="worker-1",
        raw_details=transient_miss,
        now_ts=101.0,
    )

    assert held["status"] == "compliant"
    assert "helmet" in held["detected_items"]
    assert held["missing_items"] == []

    cached = recognizer._get_live_ppe_details(102.0, person_id="worker-1")
    assert cached["status"] == "compliant"
    assert set(cached["latched_items"]) == {"helmet", "vest"}

    expired = recognizer._get_live_ppe_details(105.5, person_id="worker-1")
    assert expired["status"] == "not_evaluated"


def test_record_ppe_pass_event_writes_timestamped_ppe_log(db_session):
    recognizer = GateAttendanceRecognizer()
    person = Person(name="Helena Hardhat", employee_id="PPE-01")
    db_session.add(person)
    db_session.commit()
    db_session.refresh(person)

    attendance = Attendance(
        person_id=person.id,
        person_name=person.name,
        direction="ENTRY",
        ppe_compliant=True,
        access_granted=True,
        timestamp=datetime.utcnow(),
    )
    db_session.add(attendance)
    db_session.commit()
    db_session.refresh(attendance)

    recognizer._record_ppe_pass_event(
        db=db_session,
        person=person,
        direction="ENTRY",
        attendance=attendance,
        ppe_details={
            "status": "compliant",
            "required_items": ["helmet", "vest"],
            "detected_items": ["helmet", "vest"],
            "missing_items": [],
            "detector_confidences": {"helmet": 0.96, "vest": 0.93},
            "latched_items": ["helmet", "vest"],
            "detector_available": True,
        },
    )
    db_session.commit()

    event = (
        db_session.query(Event)
        .filter(Event.category == "PPE", Event.event_type == "PPE_ENTRY_OK")
        .one()
    )
    assert event.timestamp is not None
    assert person.id in (event.data or "")
    assert attendance.id in (event.data or "")


def test_plan_attendance_action_reports_already_checked_in_for_duplicate_entry(monkeypatch):
    recognizer = GateAttendanceRecognizer()
    recognizer.gate_direction_mode = "ENTRY"
    recognizer.min_direction_gap_seconds = 10
    now = datetime.utcnow()
    person = SimpleNamespace(id="worker-1", name="Alex Carter")

    monkeypatch.setattr(
        recognizer,
        "_get_current_shift_window",
        lambda current: ("day", now.replace(hour=6, minute=0, second=0, microsecond=0)),
    )
    monkeypatch.setattr(
        recognizer,
        "_get_last_attendance_in_shift",
        lambda person_id, shift_started_at: SimpleNamespace(
            direction="ENTRY",
            access_granted=True,
            timestamp=now,
        ),
    )

    direction, details = recognizer._plan_attendance_action(person, now)

    assert direction is None
    assert details == "Alex Carter is already checked in."


def test_plan_attendance_action_allows_immediate_checkout_after_entry(monkeypatch):
    recognizer = GateAttendanceRecognizer()
    recognizer.gate_direction_mode = "EXIT"
    recognizer.min_direction_gap_seconds = 10
    now = datetime.utcnow()
    person = SimpleNamespace(id="worker-2", name="Jamie Lin")

    monkeypatch.setattr(
        recognizer,
        "_get_current_shift_window",
        lambda current: ("day", now.replace(hour=6, minute=0, second=0, microsecond=0)),
    )
    monkeypatch.setattr(
        recognizer,
        "_get_last_attendance_in_shift",
        lambda person_id, shift_started_at: None,
    )
    monkeypatch.setattr(
        recognizer,
        "_get_latest_attendance",
        lambda person_id: SimpleNamespace(
            direction="ENTRY",
            access_granted=True,
            timestamp=now,
        ),
    )

    direction, details = recognizer._plan_attendance_action(person, now)

    assert direction == "EXIT"
    assert details == "Jamie Lin checked out from the site."
