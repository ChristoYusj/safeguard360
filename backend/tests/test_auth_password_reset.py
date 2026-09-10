from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.db.models import User
from app.services.auth import hash_password, request_password_reset
from app.services.email import EmailDeliveryError
from app.services.rbac import USER_STATUS_ACTIVE
from app.config.settings import get_settings


def build_request(base_url: str = "http://testserver"):
    return SimpleNamespace(
        headers={},
        base_url=base_url,
        client=SimpleNamespace(host="127.0.0.1"),
    )


@pytest.fixture()
def mail_settings_guard(tmp_path):
    settings = get_settings()
    original_transport = settings.MAIL_TRANSPORT
    original_outbox = settings.MAIL_LOCAL_OUTBOX_DIR
    original_expose = settings.MAIL_EXPOSE_LOCAL_RESET_LINKS
    original_frontend = settings.FRONTEND_APP_URL
    settings.MAIL_LOCAL_OUTBOX_DIR = str(tmp_path)
    settings.FRONTEND_APP_URL = "http://frontend.test"
    try:
        yield settings
    finally:
        settings.MAIL_TRANSPORT = original_transport
        settings.MAIL_LOCAL_OUTBOX_DIR = original_outbox
        settings.MAIL_EXPOSE_LOCAL_RESET_LINKS = original_expose
        settings.FRONTEND_APP_URL = original_frontend


def test_request_password_reset_local_mode_captures_email_without_exposing_url_by_default(db_session, mail_settings_guard, tmp_path):
    mail_settings_guard.MAIL_TRANSPORT = "local"
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

    result = request_password_reset(
        db=db_session,
        request=build_request(),
        email=user.email,
    )

    assert result["delivery_mode"] == "local"
    assert "local_reset_url" not in result
    captured_files = list(tmp_path.iterdir())
    assert captured_files


def test_request_password_reset_can_expose_local_reset_url_when_explicitly_enabled(db_session, mail_settings_guard):
    mail_settings_guard.MAIL_TRANSPORT = "local"
    mail_settings_guard.MAIL_EXPOSE_LOCAL_RESET_LINKS = True
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

    result = request_password_reset(
        db=db_session,
        request=build_request(),
        email=user.email,
    )

    assert result["delivery_mode"] == "local"
    # The link origin is the configured FRONTEND_APP_URL, not the request's
    # base_url ("http://testserver" here).
    assert result["local_reset_url"].startswith("http://frontend.test/auth/reset-password?token=")


def test_request_password_reset_masks_provider_errors(db_session, mail_settings_guard, monkeypatch):
    mail_settings_guard.MAIL_TRANSPORT = "resend"
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

    def fail_delivery(**_kwargs):
        raise EmailDeliveryError("Raw provider failure")

    monkeypatch.setattr("app.services.auth.send_transactional_email", fail_delivery)

    with pytest.raises(HTTPException) as exc_info:
        request_password_reset(
            db=db_session,
            request=build_request(),
            email=user.email,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Password reset delivery is currently unavailable."
