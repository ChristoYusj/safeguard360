"""WebSocket authentication and domain classification.

The sockets sit outside the HTTP middleware and authenticate themselves from
the access cookie; a wrong classification streams one module's camera to the
other module's operators (audit N5).
"""
from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

from app.websocket.manager import ConnectionManager
from tests.helpers import login_admin

ACCESS_COOKIE = "safeguard360_access"


def test_events_socket_rejects_anonymous_connections(client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/events"):
            pass
    assert exc_info.value.code == 1008


def test_live_socket_rejects_anonymous_connections(client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/live"):
            pass
    assert exc_info.value.code == 1008


def test_events_socket_sends_status_to_an_authenticated_operator(client):
    login_admin(client)
    token = client.cookies.get(ACCESS_COOKIE)
    assert token
    with client.websocket_connect("/ws/events", headers={"cookie": f"{ACCESS_COOKIE}={token}"}) as ws:
        message = ws.receive_json()
    assert message["type"] == "status"
    assert message["camera"]["active"] is False


@pytest.mark.parametrize(
    "status,expected",
    [
        ({"mode": "idle", "owner_module": "attendance"}, "gate"),
        ({"mode": "idle", "owner_module": "drivers"}, "driver"),
        ({"mode": "gate", "owner_module": None}, "gate"),
        ({"mode": "driver", "owner_module": None}, "driver"),
        ({"mode": "idle", "owner_module": None}, "generic"),
    ],
)
def test_status_domain_follows_the_owning_module_first(status, expected):
    assert ConnectionManager._classify_status_domain(status) == expected


@pytest.mark.parametrize(
    "role,domain,allowed",
    [
        ("fleet_operator", "gate", False),
        ("fleet_operator", "driver", True),
        ("safety_operator", "gate", True),
        ("safety_operator", "driver", False),
        ("general_manager", "gate", True),
        ("admin", "driver", True),
        (None, "gate", False),
        (None, "generic", True),
    ],
)
def test_domain_gate_per_role(role, domain, allowed):
    assert ConnectionManager._can_receive_domain(role, domain) is allowed
