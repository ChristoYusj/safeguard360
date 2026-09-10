"""HTTP smoke tests over the real application.

These go through create_app(): lifespan (init_db + bootstrap admin seed), the
auth middleware, RBAC and the routers, on a StaticPool in-memory database that
the request thread shares with the test. They exist so later security fixes can
be proven over HTTP rather than by calling handlers directly.
"""
from __future__ import annotations

import os

ACCESS_COOKIE = "safeguard360_access"
REFRESH_COOKIE = "safeguard360_refresh"


def _login(client):
    return client.post(
        "/api/auth/login",
        json={
            "email": os.environ["ADMIN_EMAIL"],
            "password": os.environ["BOOTSTRAP_ADMIN_PASSWORD"],
        },
    )


def test_protected_route_requires_a_session(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}


def test_camera_state_requires_a_session(client):
    assert client.get("/api/camera/state").status_code == 401


def test_bootstrap_admin_logs_in_and_reads_own_profile(client):
    response = _login(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["email"] == os.environ["ADMIN_EMAIL"]
    assert body["user"]["role"] == "admin"
    assert ACCESS_COOKIE in client.cookies
    assert REFRESH_COOKIE in client.cookies

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == os.environ["ADMIN_EMAIL"]


def test_wrong_password_is_rejected(client):
    response = client.post(
        "/api/auth/login",
        json={"email": os.environ["ADMIN_EMAIL"], "password": "not-the-password"},
    )
    assert response.status_code == 401
    assert ACCESS_COOKIE not in client.cookies


def test_logged_in_admin_sees_idle_camera_state(client):
    assert _login(client).status_code == 200
    state = client.get("/api/camera/state")
    assert state.status_code == 200
    payload = state.json()
    assert payload["active"] is False
    assert "mode" in payload


def test_each_test_gets_a_fresh_database(client):
    # The previous test logged in; a new fixture instance must not carry that
    # session or any state over. Only the seeded admin exists.
    assert client.get("/api/auth/me").status_code == 401
    assert _login(client).status_code == 200
    users = client.get("/api/admin/users")
    assert users.status_code == 200
    assert [u["email"] for u in users.json()["users"]] == [os.environ["ADMIN_EMAIL"]]
