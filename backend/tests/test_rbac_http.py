"""The permission model, exercised over HTTP for every role.

One table, read top to bottom: which role may reach which route. Each case
logs in as a real user and goes through the auth middleware, rbac and the
handler's own guards together.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.camera import _assert_camera_access
from app.services.rbac import (
    ADMIN_ROLE,
    FLEET_OPERATOR_ROLE,
    GENERAL_MANAGER_ROLE,
    SAFETY_OPERATOR_ROLE,
)
from tests.helpers import create_user, login_admin, login_as

OK = "ok"
FORBIDDEN = "forbidden"

# (method, path, {role: expectation}). Routes with side effects beyond an
# empty in-memory database are avoided; mutations use bodies that are rejected
# by RBAC before validation.
MATRIX = [
    ("GET", "/api/auth/me", {ADMIN_ROLE: OK, GENERAL_MANAGER_ROLE: OK, SAFETY_OPERATOR_ROLE: OK, FLEET_OPERATOR_ROLE: OK}),
    ("GET", "/api/admin/users", {ADMIN_ROLE: OK, GENERAL_MANAGER_ROLE: FORBIDDEN, SAFETY_OPERATOR_ROLE: FORBIDDEN, FLEET_OPERATOR_ROLE: FORBIDDEN}),
    ("GET", "/api/attendance", {ADMIN_ROLE: OK, GENERAL_MANAGER_ROLE: OK, SAFETY_OPERATOR_ROLE: OK, FLEET_OPERATOR_ROLE: FORBIDDEN}),
    ("DELETE", "/api/attendance/logs", {ADMIN_ROLE: OK, GENERAL_MANAGER_ROLE: FORBIDDEN, SAFETY_OPERATOR_ROLE: FORBIDDEN, FLEET_OPERATOR_ROLE: FORBIDDEN}),
    ("GET", "/api/persons", {ADMIN_ROLE: OK, GENERAL_MANAGER_ROLE: OK, SAFETY_OPERATOR_ROLE: OK, FLEET_OPERATOR_ROLE: FORBIDDEN}),
    ("POST", "/api/persons", {ADMIN_ROLE: None, GENERAL_MANAGER_ROLE: FORBIDDEN, SAFETY_OPERATOR_ROLE: FORBIDDEN, FLEET_OPERATOR_ROLE: FORBIDDEN}),
    ("GET", "/api/events", {ADMIN_ROLE: OK, GENERAL_MANAGER_ROLE: OK, SAFETY_OPERATOR_ROLE: OK, FLEET_OPERATOR_ROLE: OK}),
    ("GET", "/api/alerts", {ADMIN_ROLE: OK, GENERAL_MANAGER_ROLE: OK, SAFETY_OPERATOR_ROLE: OK, FLEET_OPERATOR_ROLE: OK}),
    ("GET", "/api/chatbot/status", {ADMIN_ROLE: OK, GENERAL_MANAGER_ROLE: OK, SAFETY_OPERATOR_ROLE: FORBIDDEN, FLEET_OPERATOR_ROLE: FORBIDDEN}),
    ("GET", "/api/camera/state", {ADMIN_ROLE: OK, GENERAL_MANAGER_ROLE: OK, SAFETY_OPERATOR_ROLE: OK, FLEET_OPERATOR_ROLE: OK}),
    # Without an owner_module a safety or fleet operator may not switch modes.
    ("POST", "/api/camera/mode/driver", {ADMIN_ROLE: None, GENERAL_MANAGER_ROLE: None, SAFETY_OPERATOR_ROLE: FORBIDDEN, FLEET_OPERATOR_ROLE: FORBIDDEN}),
]

CASES = [
    pytest.param(method, path, role, expectation, id=f"{role}:{method} {path}")
    for method, path, expectations in MATRIX
    for role, expectation in expectations.items()
    if expectation is not None
]


def _login_role(client, role: str) -> None:
    if role == ADMIN_ROLE:
        login_admin(client)
        return
    email = f"{role}@example.com"
    create_user(email, role=role)
    login_as(client, email)


@pytest.mark.parametrize("method,path,role,expectation", CASES)
def test_role_route_matrix(client, method, path, role, expectation):
    _login_role(client, role)
    response = client.request(method, path, json={} if method == "POST" else None)
    if expectation == FORBIDDEN:
        assert response.status_code == 403, f"{role} {method} {path}: {response.status_code} {response.text}"
    else:
        assert response.status_code == 200, f"{role} {method} {path}: {response.status_code} {response.text}"


def test_anonymous_requests_are_rejected_not_forbidden(client):
    for method, path, _ in MATRIX:
        response = client.request(method, path, json={} if method == "POST" else None)
        assert response.status_code == 401, f"{method} {path}: {response.status_code}"


def test_camera_access_fails_closed_for_unknown_roles():
    request = SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(role="visitor")))
    with pytest.raises(HTTPException) as exc_info:
        _assert_camera_access(request, owner_module="attendance")
    assert exc_info.value.status_code == 403

    request = SimpleNamespace(state=SimpleNamespace())
    with pytest.raises(HTTPException) as exc_info:
        _assert_camera_access(request, owner_module="drivers", mode="driver")
    assert exc_info.value.status_code == 403
