"""Roster CSV import over HTTP.

Audit finding N37: a file that omitted a column overwrote that column with
its default, so a name-only correction file re-activated offboarded workers
and cleared their shift.
"""
from __future__ import annotations

from app.db.connection import SessionLocal
from app.db.models import Person
from tests.helpers import login_admin


def _seed_offboarded_worker() -> str:
    db = SessionLocal()
    try:
        person = Person(name="Nadia K.", employee_id="EMP-1", shift_id="night", is_active=False)
        db.add(person)
        db.commit()
        db.refresh(person)
        return person.id
    finally:
        db.close()


def _person(person_id: str) -> dict:
    db = SessionLocal()
    try:
        person = db.get(Person, person_id)
        return {"name": person.name, "shift_id": person.shift_id, "is_active": person.is_active}
    finally:
        db.close()


def _upload(client, csv_text: str):
    return client.post(
        "/api/persons/bulk-import",
        files={"file": ("roster.csv", csv_text.encode("utf-8"), "text/csv")},
    )


def test_name_only_file_leaves_shift_and_active_flag_alone(client):
    login_admin(client)
    person_id = _seed_offboarded_worker()

    response = _upload(client, "name,employee_id\nNadia Khoury,EMP-1\n")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["updated"] == 1
    assert body["reactivated"] == 0
    assert _person(person_id) == {"name": "Nadia Khoury", "shift_id": "night", "is_active": False}


def test_explicit_is_active_column_reactivates_and_reports_it(client):
    login_admin(client)
    person_id = _seed_offboarded_worker()

    response = _upload(client, "name,employee_id,is_active\nNadia K.,EMP-1,true\n")

    assert response.status_code == 200, response.text
    assert response.json()["reactivated"] == 1
    assert _person(person_id)["is_active"] is True
