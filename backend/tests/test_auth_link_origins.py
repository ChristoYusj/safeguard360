"""Emailed links must never take their origin from the incoming request.

Audit finding C1: with FRONTEND_APP_URL blank (the old default) the reset
link fell back to the Origin/Referer headers and the approval links to the
Host header, so a forged request put a live token on the attacker's domain.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.config.settings import Settings, get_settings
from app.db.models import User
from app.services.auth import build_approval_urls, build_password_reset_url, hash_password
from app.services.rbac import USER_STATUS_ACTIVE


def hostile_request():
    return SimpleNamespace(
        headers={"origin": "https://evil.tld", "referer": "https://evil.tld/auth/reset"},
        base_url="https://evil.tld/",
        client=SimpleNamespace(host="203.0.113.9"),
    )


@pytest.fixture()
def link_settings():
    settings = get_settings()
    original = (settings.FRONTEND_APP_URL, settings.PUBLIC_API_BASE_URL)
    settings.FRONTEND_APP_URL = "https://portal.example.test"
    settings.PUBLIC_API_BASE_URL = ""
    try:
        yield settings
    finally:
        settings.FRONTEND_APP_URL, settings.PUBLIC_API_BASE_URL = original


def _user(db_session) -> User:
    user = User(
        full_name="Chris Operator",
        email="chris@example.com",
        role="safety_operator",
        role_department="Safety Operator",
        password_hash=hash_password("Password123!"),
        status=USER_STATUS_ACTIVE,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_password_reset_link_ignores_request_headers(db_session, link_settings):
    url = build_password_reset_url(hostile_request(), _user(db_session))
    assert url.startswith("https://portal.example.test/auth/reset-password?token=")
    assert "evil.tld" not in url


def test_approval_links_ignore_the_host_header(db_session, link_settings):
    approve, reject = build_approval_urls(hostile_request(), _user(db_session))
    assert approve.startswith("https://portal.example.test/api/auth/approval/approve?token=")
    assert reject.startswith("https://portal.example.test/api/auth/approval/reject?token=")


def test_public_api_base_url_overrides_the_api_link_origin(db_session, link_settings):
    link_settings.PUBLIC_API_BASE_URL = "https://api.example.test/"
    approve, _ = build_approval_urls(hostile_request(), _user(db_session))
    assert approve.startswith("https://api.example.test/api/auth/approval/approve?token=")


def test_blank_frontend_url_is_refused_rather_than_guessed(db_session, link_settings):
    link_settings.FRONTEND_APP_URL = ""
    with pytest.raises(HTTPException) as exc_info:
        build_password_reset_url(hostile_request(), _user(db_session))
    assert exc_info.value.status_code == 503


def test_frontend_url_is_a_required_setting():
    settings = Settings(
        _env_file=None,
        JWT_ACCESS_SECRET="a",
        JWT_REFRESH_SECRET="b",
        JWT_APPROVAL_SECRET="c",
        ADMIN_EMAIL="admin@example.com",
        TOTP_ENCRYPTION_KEY="k",
        FRONTEND_APP_URL="",
    )
    assert "FRONTEND_APP_URL" in settings.missing_required_auth_settings
