"""Audit-log administration over HTTP (audit finding N7)."""
from __future__ import annotations

from app.db.connection import SessionLocal
from app.db.models import AuditLog
from tests.helpers import login_admin


def test_clearing_the_audit_log_leaves_a_record_of_the_clear(client):
    login_admin(client)  # writes a login_success row
    db = SessionLocal()
    try:
        assert db.query(AuditLog).count() >= 1
    finally:
        db.close()

    response = client.delete("/api/admin/audit-logs")

    assert response.status_code == 200, response.text
    assert response.json()["deleted_count"] >= 1
    db = SessionLocal()
    try:
        remaining = db.query(AuditLog).all()
        assert [row.event_type for row in remaining] == ["audit_log_cleared"]
        assert remaining[0].operator_email == "admin@example.com"
        assert str(response.json()["deleted_count"]) in remaining[0].detail
    finally:
        db.close()
