"""Attendance routes over HTTP: who may do what, and who gets the credit.

Audit findings C3 (anyone could wipe the logs), C4 (client-forged recogniser
scans) and C5 (client-supplied review attribution).
"""
from __future__ import annotations

from app.db.connection import SessionLocal
from app.db.models import Attendance, AuditLog, GateReview, Person
from app.services.rbac import SAFETY_OPERATOR_ROLE
from tests.helpers import create_user, login_admin, login_as

OPERATOR = "operator@example.com"


def _seed_person() -> str:
    db = SessionLocal()
    try:
        person = Person(name="Alice Worker", employee_id="A-01")
        db.add(person)
        db.commit()
        db.refresh(person)
        return person.id
    finally:
        db.close()


def _seed_pending_review(person_id: str) -> str:
    db = SessionLocal()
    try:
        review = GateReview(
            person_id=person_id,
            person_name="Alice Worker",
            suggested_direction="ENTRY",
            status="PENDING",
        )
        db.add(review)
        db.commit()
        db.refresh(review)
        return review.id
    finally:
        db.close()


def _audit_rows(event_type: str):
    db = SessionLocal()
    try:
        return [
            (row.operator_email, row.detail)
            for row in db.query(AuditLog).filter(AuditLog.event_type == event_type).all()
        ]
    finally:
        db.close()


def test_safety_operator_cannot_clear_attendance_logs(client):
    create_user(OPERATOR, role=SAFETY_OPERATOR_ROLE)
    login_as(client, OPERATOR)

    response = client.delete("/api/attendance/logs")

    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden."}


def test_admin_clear_is_written_to_the_audit_log(client):
    login_admin(client)
    person_id = _seed_person()
    db = SessionLocal()
    try:
        db.add(
            Attendance(
                person_id=person_id,
                person_name="Alice Worker",
                direction="ENTRY",
                ppe_compliant=True,
                access_granted=True,
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.delete("/api/attendance/logs")

    assert response.status_code == 200, response.text
    assert response.json()["attendance_deleted"] == 1
    rows = _audit_rows("attendance_cleared")
    assert len(rows) == 1
    assert rows[0][0] == "admin@example.com"
    assert "1 attendance records" in rows[0][1]


def test_manual_entry_cannot_masquerade_as_a_recogniser_scan(client):
    create_user(OPERATOR, role=SAFETY_OPERATOR_ROLE)
    login_as(client, OPERATOR)
    person_id = _seed_person()

    response = client.post(
        "/api/attendance",
        json={
            "person_id": person_id,
            "direction": "ENTRY",
            "access_granted": True,
            "ppe_compliant": True,
            # Both of these used to be honoured verbatim.
            "confidence": 0.99,
            "log_method": "AUTO",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["log_method"] == "MANUAL"
    assert body["confidence"] is None
    rows = _audit_rows("attendance_manual_entry")
    assert len(rows) == 1
    assert rows[0][0] == OPERATOR
    assert body["id"] in rows[0][1]


def test_review_decision_is_attributed_to_the_session_user(client):
    create_user(OPERATOR, role=SAFETY_OPERATOR_ROLE)
    login_as(client, OPERATOR)
    review_id = _seed_pending_review(_seed_person())

    response = client.post(
        f"/api/attendance/reviews/{review_id}/decision",
        json={"decision": "DENIED", "decided_by": "colleague@example.com"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["decided_by"] == OPERATOR
    db = SessionLocal()
    try:
        assert db.get(GateReview, review_id).decided_by == OPERATOR
    finally:
        db.close()
