"""One owner for "who is on site" (audit finding N53).

The gate scanned the whole attendance table, the assistant ran its own
grouped query, and the Attendance page derived the same set in the browser
from the most recent page of records. A worker whose entry fell outside that
page was on site according to two of them and off site according to the
third, and the answer drives the Check-In/Check-Out locks.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.db.connection import SessionLocal
from app.db.models import Attendance, Person
from app.services.attendance_state import get_on_site_person_ids, get_on_site_workers
from app.services.chatbot import build_site_context
from app.services.gate_attendance import GateAttendanceRecognizer
from app.services.rbac import FLEET_OPERATOR_ROLE, SAFETY_OPERATOR_ROLE
from tests.helpers import create_user, login_admin, login_as

BASE = datetime(2026, 9, 11, 8, 0, 0)


def _person(db, name: str, employee_id: str, shift_id: str | None = None) -> Person:
    person = Person(name=name, employee_id=employee_id, shift_id=shift_id)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def _log(db, person: Person, direction: str, minutes: int, *, granted: bool = True) -> Attendance:
    record = Attendance(
        person_id=person.id,
        person_name=person.name,
        direction=direction,
        timestamp=BASE + timedelta(minutes=minutes),
        access_granted=granted,
        ppe_compliant=True,
    )
    db.add(record)
    db.commit()
    return record


def _seed() -> dict:
    """Nadia is in, Omar came and went, Rami was refused, Lina never appeared."""
    db = SessionLocal()
    try:
        nadia = _person(db, "Nadia K.", "EMP-1", "day")
        omar = _person(db, "Omar S.", "EMP-2")
        rami = _person(db, "Rami T.", "EMP-3")
        lina = _person(db, "Lina H.", "EMP-4")

        _log(db, nadia, "ENTRY", 0)
        _log(db, omar, "ENTRY", 1)
        _log(db, omar, "EXIT", 30)
        _log(db, rami, "ENTRY", 2, granted=False)
        return {"nadia": nadia.id, "omar": omar.id, "rami": rami.id, "lina": lina.id}
    finally:
        db.close()


def test_only_a_worker_whose_latest_record_is_a_granted_entry_is_on_site(client):
    ids = _seed()

    db = SessionLocal()
    try:
        on_site = get_on_site_workers(db)
    finally:
        db.close()

    assert [worker.person_id for worker in on_site] == [ids["nadia"]]
    assert on_site[0].name == "Nadia K."
    assert on_site[0].employee_id == "EMP-1"
    assert on_site[0].shift_id == "day"
    assert on_site[0].entered_at == BASE


def test_a_later_entry_puts_a_worker_back_on_site(client):
    ids = _seed()

    db = SessionLocal()
    try:
        omar = db.get(Person, ids["omar"])
        _log(db, omar, "ENTRY", 45)
        assert get_on_site_person_ids(db) == {ids["nadia"], ids["omar"]}
    finally:
        db.close()


def test_the_endpoint_is_the_same_answer(client):
    ids = _seed()
    login_admin(client)

    response = client.get("/api/attendance/on-site")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 1
    assert [worker["person_id"] for worker in body["workers"]] == [ids["nadia"]]
    assert body["workers"][0]["entered_at"] == BASE.isoformat()


def test_the_gate_and_the_assistant_agree_with_the_endpoint(client):
    """Three implementations, one answer. They used to be able to differ."""
    ids = _seed()
    login_admin(client)

    endpoint = {w["person_id"] for w in client.get("/api/attendance/on-site").json()["workers"]}

    recognizer = GateAttendanceRecognizer()
    recognizer.on_site_cache_loaded_at = 0.0  # skip the 3 s cache
    gate = recognizer._get_on_site_person_ids(BASE)

    db = SessionLocal()
    try:
        assistant = {entry["person_id"] for entry in build_site_context(db).on_site}
    finally:
        db.close()

    assert endpoint == gate == assistant == {ids["nadia"]}


def test_the_roster_is_reachable_by_the_operators_who_need_it(client):
    _seed()
    create_user("so@example.com", role=SAFETY_OPERATOR_ROLE)
    login_as(client, "so@example.com")
    assert client.get("/api/attendance/on-site").status_code == 200

    create_user("fo@example.com", role=FLEET_OPERATOR_ROLE)
    login_as(client, "fo@example.com")
    assert client.get("/api/attendance/on-site").status_code == 403


def test_two_records_sharing_a_timestamp_count_once(client):
    """The assistant used to report one worker as two people on site.

    Its query joined on max(timestamp), so when a gate write and a manual
    entry landed in the same second both rows came back and both were
    appended. The gate service, which built a set, said one. Ties are now
    broken by the record id and the newest row wins outright.
    """
    db = SessionLocal()
    try:
        nadia = _person(db, "Nadia K.", "EMP-1")
        _log(db, nadia, "ENTRY", 0)
        _log(db, nadia, "ENTRY", 0)  # same timestamp, e.g. gate + manual entry

        assert [w.person_id for w in get_on_site_workers(db)] == [nadia.id]
        context = build_site_context(db)
        assert context.on_site_count == 1
        assert len(context.on_site) == 1
    finally:
        db.close()


def test_a_tie_between_an_entry_and_an_exit_is_decided_the_same_way_every_time(client):
    db = SessionLocal()
    try:
        omar = _person(db, "Omar S.", "EMP-2")
        _log(db, omar, "ENTRY", 0)
        _log(db, omar, "EXIT", 0)  # identical timestamp

        answers = {frozenset(get_on_site_person_ids(db)) for _ in range(5)}
        assert len(answers) == 1, "the same data gave different answers"
    finally:
        db.close()


def test_an_empty_site_is_an_empty_list_not_an_error(client):
    login_admin(client)

    body = client.get("/api/attendance/on-site").json()

    assert body == {"count": 0, "workers": []}
