"""GET /api/camera/state shows each role only its own domain (audit N4)."""
from __future__ import annotations

import dataclasses

import pytest

from app.camera.manager import camera_manager
from app.services.rbac import FLEET_OPERATOR_ROLE, SAFETY_OPERATOR_ROLE
from tests.helpers import create_user, login_admin, login_as

SECRET_STREAM = "rtsp://gate-user:s3cret@10.0.0.5/stream1"


@pytest.fixture()
def gate_camera_running(monkeypatch):
    real_state = camera_manager.get_state()
    fake_state = dataclasses.replace(
        real_state, active=True, mode="gate", source_type="ip_stream", source_id=SECRET_STREAM
    )
    monkeypatch.setattr(camera_manager, "get_state", lambda: fake_state)
    monkeypatch.setattr(
        camera_manager,
        "get_gate_state",
        lambda: {"match_status": "matched", "person_name": "Alice Worker", "confidence": 0.93},
    )
    return fake_state


def test_admin_sees_the_full_gate_payload(client, gate_camera_running):
    login_admin(client)
    body = client.get("/api/camera/state").json()
    assert body["gate"]["person_name"] == "Alice Worker"
    assert body["source_id"] == SECRET_STREAM


def test_safety_operator_sees_gate_payload_but_not_stream_credentials(client, gate_camera_running):
    create_user("safety@example.com", role=SAFETY_OPERATOR_ROLE)
    login_as(client, "safety@example.com")
    body = client.get("/api/camera/state").json()
    assert body["gate"]["person_name"] == "Alice Worker"
    assert body["source_id"] == "rtsp://***@10.0.0.5/stream1"


def test_fleet_operator_never_sees_gate_identity(client, gate_camera_running):
    create_user("fleet@example.com", role=FLEET_OPERATOR_ROLE)
    login_as(client, "fleet@example.com")
    body = client.get("/api/camera/state").json()
    assert body["gate"] is None
    assert "s3cret" not in body["source_id"]
    assert body["mode"] == "gate"
