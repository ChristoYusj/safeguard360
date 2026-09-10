from __future__ import annotations

from types import SimpleNamespace

import pytest

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


def _active_user(db_session) -> User:
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
    return user


def test_request_password_reset_local_mode_captures_email_and_returns_nothing(
    db_session, mail_settings_guard, tmp_path
):
    mail_settings_guard.MAIL_TRANSPORT = "local"
    user = _active_user(db_session)

    result = request_password_reset(db=db_session, request=build_request(), email=user.email)

    # The response never says whether the account exists (audit H5): the
    # captured email on disk is the only evidence anything happened.
    assert result == {}
    assert list(tmp_path.iterdir())


def test_request_password_reset_can_expose_local_reset_url_when_explicitly_enabled(
    db_session, mail_settings_guard
):
    mail_settings_guard.MAIL_TRANSPORT = "local"
    mail_settings_guard.MAIL_EXPOSE_LOCAL_RESET_LINKS = True
    user = _active_user(db_session)

    result = request_password_reset(db=db_session, request=build_request(), email=user.email)

    # The link origin is the configured FRONTEND_APP_URL, not the request's
    # base_url ("http://testserver" here).
    assert set(result) == {"local_reset_url"}
    assert result["local_reset_url"].startswith("http://frontend.test/auth/reset-password?token=")


def test_request_password_reset_swallows_provider_errors(db_session, mail_settings_guard, monkeypatch):
    mail_settings_guard.MAIL_TRANSPORT = "resend"
    user = _active_user(db_session)

    def fail_delivery(**_kwargs):
        raise EmailDeliveryError("Raw provider failure")

    monkeypatch.setattr("app.services.auth.send_transactional_email", fail_delivery)

    # A 503 only for registered addresses was an account-existence oracle; the
    # failure is logged server-side and the caller sees the generic result.
    assert request_password_reset(db=db_session, request=build_request(), email=user.email) == {}


def test_request_password_reset_for_unknown_email_returns_nothing(db_session, mail_settings_guard):
    mail_settings_guard.MAIL_TRANSPORT = "local"
    assert request_password_reset(db=db_session, request=build_request(), email="nobody@example.com") == {}
