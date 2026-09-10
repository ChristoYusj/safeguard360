"""Admin-only controls and audit coverage (audit findings H6, H7, N12, N42, N45)."""
from __future__ import annotations

import os

from app.db.connection import SessionLocal
from app.db.models import Attendance, AuditLog, Person, User
from app.services import persons as persons_service
from app.services.auth import (
    backfill_user_roles,
    create_approval_token,
    hash_password,
    serialize_user,
)
from app.services.rbac import (
    ADMIN_ROLE,
    GENERAL_MANAGER_ROLE,
    SAFETY_OPERATOR_ROLE,
    USER_STATUS_PENDING,
    derive_legacy_role,
)
from tests.helpers import create_user, login_admin, login_as


def _audit(event_type: str) -> list[tuple[str, str]]:
    db = SessionLocal()
    try:
        return [
            (row.operator_email, row.detail or "")
            for row in db.query(AuditLog).filter(AuditLog.event_type == event_type).all()
        ]
    finally:
        db.close()


# --- H6: the PPE policy is a management control ----------------------------


def test_safety_operator_cannot_change_the_ppe_policy(client):
    create_user("so@example.com", role=SAFETY_OPERATOR_ROLE)
    login_as(client, "so@example.com")

    response = client.put("/api/attendance/ppe-policy", json={"deny_non_compliant_entry": False})

    assert response.status_code == 403
    assert _audit("ppe_policy_changed") == []


def test_manager_policy_change_is_audited_with_before_and_after(client):
    create_user("gm@example.com", role=GENERAL_MANAGER_ROLE)
    login_as(client, "gm@example.com")
    before = client.get("/api/attendance/ppe-policy").json()["require_helmet"]

    response = client.put("/api/attendance/ppe-policy", json={"require_helmet": not before})

    assert response.status_code == 200, response.text
    assert response.json()["require_helmet"] is (not before)
    rows = _audit("ppe_policy_changed")
    assert len(rows) == 1
    assert rows[0][0] == "gm@example.com"
    assert f"require_helmet {before} -> {not before}" in rows[0][1]


# --- H7: emailed approval links no longer act on GET -----------------------


def _pending_user_and_token() -> tuple[str, str]:
    db = SessionLocal()
    try:
        user = User(
            full_name="Pending Person",
            email="pending@example.com",
            role=SAFETY_OPERATOR_ROLE,
            role_department="Safety Operator",
            password_hash=hash_password("Str0ng-Passw0rd!"),
            status=USER_STATUS_PENDING,
            approval_token_version=0,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id, create_approval_token(user, "approve")
    finally:
        db.close()


def _status_of(user_id: str) -> str:
    db = SessionLocal()
    try:
        return db.get(User, user_id).status
    finally:
        db.close()


def test_opening_the_approval_link_shows_a_confirmation_and_changes_nothing(client):
    user_id, token = _pending_user_and_token()

    response = client.get(f"/api/auth/approval/approve?token={token}")

    assert response.status_code == 200
    assert 'method="post"' in response.text
    assert "pending@example.com" in response.text
    assert _status_of(user_id) == "pending"


def test_posting_the_confirmation_approves_exactly_once(client):
    user_id, token = _pending_user_and_token()

    first = client.post("/api/auth/approval/approve", data={"token": token})
    assert first.status_code == 200, first.text
    assert _status_of(user_id) == "active"

    again = client.post("/api/auth/approval/approve", data={"token": token})
    assert again.status_code == 401


# --- N12: ADMIN_EMAIL no longer overrides a stored role ----------------------


def test_admin_email_no_longer_overrides_a_stored_role(client):
    admin_email = os.environ["ADMIN_EMAIL"]
    assert derive_legacy_role(GENERAL_MANAGER_ROLE, admin_email) == GENERAL_MANAGER_ROLE
    assert derive_legacy_role("Admin", "anyone@example.com") == ADMIN_ROLE  # legacy label still maps
    assert derive_legacy_role(None, "anyone@example.com") == GENERAL_MANAGER_ROLE

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == admin_email).first()
        admin.role = GENERAL_MANAGER_ROLE
        db.commit()
        backfill_user_roles(db)  # ran at every startup and used to re-promote
        db.commit()
        db.refresh(admin)
        assert admin.role == GENERAL_MANAGER_ROLE
        assert serialize_user(admin)["role"] == GENERAL_MANAGER_ROLE
    finally:
        db.close()


# --- N42: the gate allow-list is audited ------------------------------------


def test_person_mutations_are_attributed_in_the_audit_log(client):
    login_admin(client)

    created = client.post("/api/persons", json={"name": "Nadia K.", "employee_id": "EMP-7"})
    assert created.status_code == 201, created.text
    person_id = created.json()["id"]
    assert _audit("person_enrolled")[0][0] == "admin@example.com"

    updated = client.put(f"/api/persons/{person_id}", json={"name": "Nadia Khoury", "shift_id": "night"})
    assert updated.status_code == 200, updated.text
    assert "Nadia Khoury" in _audit("person_updated")[0][1]

    imported = client.post(
        "/api/persons/bulk-import",
        files={"file": ("roster.csv", b"name,employee_id\nAli,EMP-8\n", "text/csv")},
    )
    assert imported.status_code == 200, imported.text
    assert "1 created" in _audit("roster_imported")[0][1]

    deactivated = client.delete(f"/api/persons/{person_id}")
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["is_active"] is False
    assert person_id in _audit("person_deactivated")[0][1]


# --- N45: "delete" can actually erase ---------------------------------------


def test_purge_erases_biometrics_photos_snapshots_and_names(client, tmp_path, monkeypatch):
    monkeypatch.setattr(persons_service, "FACES_DIR", tmp_path / "faces")
    monkeypatch.setattr(persons_service, "ATTENDANCE_SNAPSHOTS_DIR", tmp_path / "attendance")
    login_admin(client)

    db = SessionLocal()
    try:
        person = Person(name="Nadia K.", employee_id="EMP-9", embedding='{"vectors": [[0.1, 0.2]]}')
        db.add(person)
        db.commit()
        db.refresh(person)
        person_id = person.id
        face_dir = tmp_path / "faces" / person_id
        face_dir.mkdir(parents=True)
        (face_dir / "thumbnail.jpg").write_bytes(b"jpg")
        person.thumbnail_path = f"data/faces/{person_id}/thumbnail.jpg"
        attendance = Attendance(
            person_id=person_id,
            person_name="Nadia K.",
            direction="ENTRY",
            ppe_compliant=True,
            access_granted=True,
            snapshot_path="data/attendance/x/snapshot.jpg",
        )
        db.add(attendance)
        db.commit()
        db.refresh(attendance)
        attendance_id = attendance.id
    finally:
        db.close()
    snapshot_dir = tmp_path / "attendance" / attendance_id
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "snapshot.jpg").write_bytes(b"jpg")

    response = client.delete(f"/api/persons/{person_id}?purge=true")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_active"] is False
    assert body["has_embedding"] is False
    assert body["name"].startswith("Removed worker")
    assert not body.get("thumbnail_data_url")
    assert not face_dir.exists()
    assert not snapshot_dir.exists()
    db = SessionLocal()
    try:
        purged = db.get(Person, person_id)
        assert purged.embedding is None
        assert purged.thumbnail_path is None
        assert purged.employee_id is None
        record = db.get(Attendance, attendance_id)
        assert record.person_name.startswith("Removed worker")
        assert record.snapshot_path is None
    finally:
        db.close()
    rows = _audit("person_purged")
    assert len(rows) == 1
    assert "Nadia K." in rows[0][1]
