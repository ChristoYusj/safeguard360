"""Events and alerts are scoped to the caller's domain (audit finding N1).

Before: /api/events and /api/alerts were granted to fleet operators and denied
to safety operators, although every persisted event was a gate-side PPE
event, and an acknowledgement recorded nobody.
"""
from __future__ import annotations

from app.db.connection import SessionLocal
from app.db.models import AuditLog
from app.services.gate_compliance import create_alert_record, create_event_record
from app.services.rbac import FLEET_OPERATOR_ROLE, GENERAL_MANAGER_ROLE, SAFETY_OPERATOR_ROLE
from tests.helpers import create_user, login_as

SAFETY = "safety@example.com"
FLEET = "fleet@example.com"
MANAGER = "manager@example.com"


def _seed_one_of_each() -> dict:
    db = SessionLocal()
    try:
        ppe_event = create_event_record(
            db, category="PPE", event_type="PPE_ENTRY_DENIED", severity="ALERT", message="Helmet missing"
        )
        ppe_alert = create_alert_record(
            db, event=ppe_event, severity="ALERT", title="PPE Violation", message="Helmet missing"
        )
        driver_event = create_event_record(
            db, category="DRIVER", event_type="fatigue_alert", severity="WARN", message="Driver fatigue"
        )
        driver_alert = create_alert_record(
            db, event=driver_event, severity="WARN", title="Driver fatigue", message="Eyes closed"
        )
        db.commit()
        return {"ppe_alert": ppe_alert.id, "driver_alert": driver_alert.id}
    finally:
        db.close()


def _categories(client, path: str) -> list[str]:
    response = client.get(path)
    assert response.status_code == 200, response.text
    return sorted(item["category"] for item in response.json())


def test_safety_operator_sees_only_gate_side_events_and_alerts(client):
    _seed_one_of_each()
    create_user(SAFETY, role=SAFETY_OPERATOR_ROLE)
    login_as(client, SAFETY)

    assert _categories(client, "/api/events") == ["PPE"]
    assert _categories(client, "/api/alerts") == ["PPE"]


def test_fleet_operator_sees_only_driver_side_events_and_alerts(client):
    _seed_one_of_each()
    create_user(FLEET, role=FLEET_OPERATOR_ROLE)
    login_as(client, FLEET)

    assert _categories(client, "/api/events") == ["DRIVER"]
    assert _categories(client, "/api/alerts") == ["DRIVER"]


def test_manager_sees_both_domains(client):
    _seed_one_of_each()
    create_user(MANAGER, role=GENERAL_MANAGER_ROLE)
    login_as(client, MANAGER)

    assert _categories(client, "/api/events") == ["DRIVER", "PPE"]


def test_acknowledging_an_alert_outside_your_domain_is_forbidden(client):
    ids = _seed_one_of_each()
    create_user(FLEET, role=FLEET_OPERATOR_ROLE)
    login_as(client, FLEET)

    response = client.post(f"/api/alerts/{ids['ppe_alert']}/ack")

    assert response.status_code == 403


def test_acknowledgement_is_attributed_in_the_audit_log(client):
    ids = _seed_one_of_each()
    create_user(SAFETY, role=SAFETY_OPERATOR_ROLE)
    login_as(client, SAFETY)

    response = client.post(f"/api/alerts/{ids['ppe_alert']}/ack")

    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False
    db = SessionLocal()
    try:
        rows = db.query(AuditLog).filter(AuditLog.event_type == "alert_acknowledged").all()
        assert [(r.operator_email, ids["ppe_alert"] in (r.detail or "")) for r in rows] == [(SAFETY, True)]
    finally:
        db.close()
