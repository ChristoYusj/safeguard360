"""reset_admin_password.py is the break-glass path (audit finding N46).

It used to rewrite only the bcrypt hash, so a stolen refresh cookie kept
minting access tokens for up to seven days and a lost authenticator locked
the site out of the admin routes for good.
"""
from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from app.db.connection import SessionLocal
from app.db.models import AuditLog, User
from app.services.auth import verify_password

REPO_ROOT = Path(__file__).resolve().parents[2]


def _script():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    return importlib.import_module("reset_admin_password")


def test_reset_script_revokes_sessions_clears_lockout_and_can_disable_2fa(client):
    email = os.environ["ADMIN_EMAIL"]
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == email).first()
        admin.password_hash = "not-a-real-hash"
        admin.refresh_token = "stale-refresh-token"
        admin.password_reset_token_version = 3
        admin.failed_login_attempts = 5
        admin.lockout_until = datetime.utcnow() + timedelta(minutes=30)
        admin.two_factor_enabled = True
        admin.two_factor_secret = "encrypted-secret"
        admin.backup_codes = "[]"
        admin.status = "restricted"
        db.commit()
    finally:
        db.close()

    assert _script().main(["--disable-2fa"]) == 0

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == email).first()
        assert verify_password(os.environ["BOOTSTRAP_ADMIN_PASSWORD"], admin.password_hash)
        assert admin.refresh_token is None
        assert admin.password_reset_token_version == 4
        assert admin.failed_login_attempts == 0
        assert admin.lockout_until is None
        assert admin.status == "active"
        assert admin.two_factor_enabled is False
        assert admin.two_factor_secret is None
        assert admin.backup_codes is None
        rows = db.query(AuditLog).filter(AuditLog.event_type == "password_change").all()
        assert any("reset_admin_password.py" in (row.detail or "") for row in rows)
    finally:
        db.close()

    login = client.post(
        "/api/auth/login",
        json={"email": email, "password": os.environ["BOOTSTRAP_ADMIN_PASSWORD"]},
    )
    assert login.status_code == 200, login.text


def test_reset_script_keeps_two_factor_unless_asked(client):
    email = os.environ["ADMIN_EMAIL"]
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == email).first()
        admin.two_factor_enabled = True
        admin.two_factor_secret = "encrypted-secret"
        db.commit()
    finally:
        db.close()

    assert _script().main([]) == 0

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == email).first()
        assert admin.two_factor_enabled is True
        assert admin.two_factor_secret == "encrypted-secret"
    finally:
        db.close()
