"""
Tests for the Person model — especially the new shift_id column and
the additive migration story (the column must exist after create_all).
"""
from __future__ import annotations

from sqlalchemy import inspect

from app.api.persons import _create_person_record
from app.db.models import Person
from app.services import persons as person_services


def test_person_table_has_shift_id_column(db_session):
    inspector = inspect(db_session.get_bind())
    columns = {col["name"] for col in inspector.get_columns("persons")}
    assert "shift_id" in columns


def test_person_shift_id_roundtrip(db_session):
    person = Person(name="Alice", employee_id="A001", shift_id="day")
    db_session.add(person)
    db_session.commit()

    fetched = db_session.query(Person).filter(Person.employee_id == "A001").first()
    assert fetched is not None
    assert fetched.shift_id == "day"


def test_person_shift_id_nullable(db_session):
    person = Person(name="Bob")
    db_session.add(person)
    db_session.commit()

    fetched = db_session.query(Person).filter(Person.name == "Bob").first()
    assert fetched.shift_id is None


def test_person_is_active_default(db_session):
    person = Person(name="Carol")
    db_session.add(person)
    db_session.commit()
    assert person.is_active is True


def test_person_defaults_generate_uuid(db_session):
    person = Person(name="Dan")
    db_session.add(person)
    db_session.commit()
    assert person.id and len(person.id) == 36


def test_enrollment_runtime_files_live_outside_backend_watch_tree():
    assert person_services.FACES_DIR == person_services.REPO_ROOT / "data" / "faces"
    assert person_services.ATTENDANCE_SNAPSHOTS_DIR == person_services.REPO_ROOT / "data" / "attendance"
    assert person_services.TMP_DIR == person_services.REPO_ROOT / "data" / "tmp"


def test_reenrollment_reuses_inactive_employee_id(db_session):
    person = Person(
        name="Old Name",
        employee_id="LB-3914-7720",
        embedding='{"ready": true}',
        thumbnail_path="data/faces/old/thumbnail.jpg",
        is_active=False,
    )
    db_session.add(person)
    db_session.commit()

    reused = _create_person_record(
        db_session,
        name="Christo",
        employee_id="LB-3914-7720",
        is_active=True,
    )

    assert reused.id == person.id
    assert reused.name == "Christo"
    assert reused.is_active is True
    assert reused.embedding is None
    assert reused.thumbnail_path is None


def test_active_employee_id_still_blocks_duplicate_enrollment(db_session):
    db_session.add(Person(name="Christo", employee_id="LB-3914-7720", is_active=True))
    db_session.commit()

    try:
        _create_person_record(
            db_session,
            name="Duplicate",
            employee_id="LB-3914-7720",
            is_active=True,
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 409
    else:
        raise AssertionError("Expected active duplicate employee ID to be rejected.")
