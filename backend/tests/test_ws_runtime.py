"""WebSocket fan-out and event-loop hygiene (Phase 2c).

Two classes of fault:
  * every broadcast iterated the live connection set across an await, so a
    client that disconnected mid-broadcast raised "Set changed size during
    iteration" and killed the broadcast for everyone else; and the role maps
    kept an entry for every socket ever dropped;
  * the camera endpoints did seconds of blocking OpenCV work inside `async
    def`, which stalls the event loop and gets live viewers evicted by their
    own 50 ms send timeout.
"""
from __future__ import annotations

import asyncio

import pytest

from app.api import camera as camera_api
from app.camera.manager import camera_manager
from app.services.rbac import SAFETY_OPERATOR_ROLE
from app.websocket.manager import ConnectionManager
from tests.helpers import create_user, login_admin, login_as


class FakeSocket:
    """Minimal WebSocket stand-in. `on_send` runs inside the awaited send."""

    def __init__(self, name: str, on_send=None, fail: bool = False):
        self.name = name
        self.sent: list = []
        self.on_send = on_send
        self.fail = fail

    async def send_bytes(self, payload: bytes) -> None:
        await self._send(payload)

    async def send_text(self, payload: str) -> None:
        await self._send(payload)

    async def _send(self, payload) -> None:
        await asyncio.sleep(0)  # a real send yields to the loop here
        if self.on_send is not None:
            self.on_send()
        if self.fail:
            raise RuntimeError(f"{self.name} is gone")
        self.sent.append(payload)


def _manager_with(*sockets) -> ConnectionManager:
    connections = ConnectionManager()
    for socket in sockets:
        connections.live_connections.add(socket)
        connections.live_connection_roles[socket] = "admin"
        connections.events_connections.add(socket)
        connections.events_connection_roles[socket] = "admin"
    return connections


def test_a_client_leaving_mid_broadcast_does_not_abort_the_others():
    """The disconnect happens during the first socket's await, exactly as it
    does when the endpoint coroutine runs while a broadcast is in flight."""
    survivor = FakeSocket("survivor")
    connections = None

    def leave() -> None:
        connections.disconnect_live(leaver)

    leaver = FakeSocket("leaver", on_send=leave)
    connections = _manager_with(leaver, survivor)

    asyncio.run(connections.broadcast_frame(b"jpeg"))

    assert survivor.sent == [b"jpeg"], "the surviving client missed the frame"


def test_a_failed_send_forgets_the_socket_and_its_role():
    dead = FakeSocket("dead", fail=True)
    alive = FakeSocket("alive")
    connections = _manager_with(dead, alive)

    asyncio.run(connections.broadcast_frame(b"jpeg"))

    assert dead not in connections.live_connections
    assert dead not in connections.live_connection_roles, "role map leaked a dead socket"
    assert alive in connections.live_connections


def test_status_and_event_broadcasts_also_forget_dead_sockets():
    dead = FakeSocket("dead", fail=True)
    connections = _manager_with(dead)

    asyncio.run(connections.broadcast_status({"mode": "idle", "owner_module": None}))

    assert dead not in connections.events_connections
    assert dead not in connections.events_connection_roles

    revived = FakeSocket("revived", fail=True)
    connections.events_connections.add(revived)
    connections.events_connection_roles[revived] = "admin"

    asyncio.run(connections.broadcast_event({"type": "attendance_match"}))

    assert revived not in connections.events_connections
    assert revived not in connections.events_connection_roles


# --- blocking work leaves the event loop --------------------------------------


def _running_loop_seen() -> bool:
    """True when called on the event loop, False on a worker thread."""
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


@pytest.mark.parametrize(
    "path,method,target,payload",
    [
        ("/api/camera/sources", "get", None, None),
        (
            "/api/camera/start",
            "post",
            "start",
            {"source_type": "webcam", "source_id": "0", "owner_module": "attendance"},
        ),
        ("/api/camera/stop", "post", "stop", {"owner_module": "attendance"}),
    ],
)
def test_blocking_camera_work_runs_off_the_event_loop(client, monkeypatch, path, method, target, payload):
    seen = {}

    if target is None:
        def probe():
            seen["on_loop"] = _running_loop_seen()
            return []

        monkeypatch.setattr(camera_api, "_probe_camera_sources", probe)
    else:
        def work(*args, **kwargs):
            seen["on_loop"] = _running_loop_seen()
            return True

        monkeypatch.setattr(camera_manager, target, work)

    login_admin(client)
    response = getattr(client, method)(path, **({"json": payload} if payload else {}))

    assert response.status_code == 200, response.text
    assert seen.get("on_loop") is False, (
        f"{path} ran its blocking work on the event loop, which stalls every websocket client"
    )


def test_the_mode_endpoint_answers_the_operator_who_asked(client, monkeypatch):
    """It was the one camera response built without the caller's role.

    With no role the scoping falls through to its strictest branch, so the
    safety operator who had just switched gate mode on got a reply with
    gate: null and had to wait for the next poll to see it.
    """
    monkeypatch.setattr(camera_manager, "running", True)
    monkeypatch.setattr(camera_manager, "owner_module", "attendance")
    monkeypatch.setattr(camera_manager, "mode", "gate")
    monkeypatch.setattr(camera_manager, "set_mode", lambda mode: None)
    monkeypatch.setattr(camera_manager, "get_gate_state", lambda: {"match_status": "idle"})
    create_user("so@example.com", role=SAFETY_OPERATOR_ROLE)
    login_as(client, "so@example.com")

    response = client.post("/api/camera/mode/gate", json={"owner_module": "attendance"})

    assert response.status_code == 200, response.text
    assert response.json()["gate"] == {"match_status": "idle"}


def test_the_mode_endpoint_still_redacts_for_a_non_manager(client, monkeypatch):
    monkeypatch.setattr(camera_manager, "running", True)
    monkeypatch.setattr(camera_manager, "owner_module", "attendance")
    monkeypatch.setattr(camera_manager, "mode", "gate")
    monkeypatch.setattr(camera_manager, "source_type", "ip_stream")
    monkeypatch.setattr(camera_manager, "source_id", "rtsp://user:secret@10.0.0.9/stream")
    monkeypatch.setattr(camera_manager, "set_mode", lambda mode: None)
    monkeypatch.setattr(camera_manager, "get_gate_state", lambda: {})
    create_user("so2@example.com", role=SAFETY_OPERATOR_ROLE)
    login_as(client, "so2@example.com")

    body = client.post("/api/camera/mode/gate", json={"owner_module": "attendance"}).json()

    assert "secret" not in str(body)
    assert body["source_id"] == "rtsp://***@10.0.0.9/stream"
