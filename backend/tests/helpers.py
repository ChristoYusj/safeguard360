"""Helpers for HTTP tests that run against the `client` fixture.

They open sessions through app.db.connection.SessionLocal, which the fixture
has pointed at the same in-memory database the application threads use.
"""
from __future__ import annotations

import os

from app.db.connection import SessionLocal
from app.db.models import User
from app.services.auth import hash_password
from app.services.rbac import USER_STATUS_ACTIVE

DEFAULT_PASSWORD = "Operator-Passw0rd!2026"


def create_user(email: str, *, role: str, password: str = DEFAULT_PASSWORD, full_name: str = "Test Operator") -> User:
    db = SessionLocal()
    try:
        user = User(
            full_name=full_name,
            email=email,
            role=role,
            role_department=role,
            password_hash=hash_password(password),
            status=USER_STATUS_ACTIVE,
            two_factor_enabled=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def login_as(client, email: str, password: str = DEFAULT_PASSWORD):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response


def login_admin(client):
    return login_as(client, os.environ["ADMIN_EMAIL"], os.environ["BOOTSTRAP_ADMIN_PASSWORD"])
