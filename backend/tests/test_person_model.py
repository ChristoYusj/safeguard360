"""
Tests for the Person model — especially the new shift_id column and
the additive migration story (the column must exist after create_all).
"""
from __future__ import annotations

from sqlalchemy import inspect

from app.db.models import Person


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
