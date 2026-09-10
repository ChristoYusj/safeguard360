"""Authentication hygiene (audit findings C2, H4, H5, H8, N2)."""
from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pyotp

from app.config.settings import get_settings
from app.db.connection import SessionLocal
from app.db.models import AuditLog, User
from app.services.auth import (
    _build_approval_email_html,
    encrypt_totp_secret,
    generate_backup_codes,
    get_client_ip,
    hash_backup_code,
)
from app.services.rbac import SAFETY_OPERATOR_ROLE
from tests.helpers import DEFAULT_PASSWORD, create_user

TWO_FA_USER = "twofactor@example.com"
KNOWN_USER = "known@example.com"
ACCESS_COOKIE = "safeguard360_access"


def _enable_two_factor(email: str) -> str:
    secret = pyotp.random_base32()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        user.two_factor_enabled = True
        user.two_factor_secret = encrypt_totp_secret(secret)
        db.commit()
    finally:
        db.close()
    return secret


def _set_backup_codes(email: str) -> list[str]:
    plain_codes, stored = generate_backup_codes()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        user.backup_codes = stored
        db.commit()
    finally:
        db.close()
    return plain_codes


def _start_two_factor_login(client):
    response = client.post("/api/auth/login", json={"email": TWO_FA_USER, "password": DEFAULT_PASSWORD})
    assert response.status_code == 202, response.text
    assert response.json() == {"requires_two_factor": True}


def _verify(client, code: str):
    return client.post("/api/auth/2fa/verify", json={"code": code})


def _user(email: str) -> User:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        db.expunge(user)
        return user
    finally:
        db.close()


# --- C2: the second factor shares the lockout ------------------------------


def test_two_factor_step_locks_after_repeated_wrong_codes(client):
    create_user(TWO_FA_USER, role=SAFETY_OPERATOR_ROLE)
    secret = _enable_two_factor(TWO_FA_USER)
    _start_two_factor_login(client)

    statuses = [_verify(client, "000000").status_code for _ in range(5)]

    assert statuses == [401, 401, 401, 401, 429]
    # The right code is refused while the account is locked.
    assert _verify(client, pyotp.TOTP(secret).now()).status_code == 429
    assert _user(TWO_FA_USER).lockout_until is not None
    db = SessionLocal()
    try:
        failures = db.query(AuditLog).filter(AuditLog.event_type == "login_failure").count()
    finally:
        db.close()
    assert failures >= 5


def test_correct_totp_completes_login_and_resets_the_counter(client):
    create_user(TWO_FA_USER, role=SAFETY_OPERATOR_ROLE)
    secret = _enable_two_factor(TWO_FA_USER)
    _start_two_factor_login(client)
    assert _verify(client, "000000").status_code == 401

    response = _verify(client, pyotp.TOTP(secret).now())

    assert response.status_code == 200, response.text
    assert ACCESS_COOKIE in client.cookies
    assert _user(TWO_FA_USER).failed_login_attempts == 0


def test_backup_codes_are_single_use(client):
    create_user(TWO_FA_USER, role=SAFETY_OPERATOR_ROLE)
    _enable_two_factor(TWO_FA_USER)
    codes = _set_backup_codes(TWO_FA_USER)
    assert all(len(code) == 11 and code[5] == "-" for code in codes)

    _start_two_factor_login(client)
    assert _verify(client, codes[0]).status_code == 200

    client.cookies.clear()
    _start_two_factor_login(client)
    assert _verify(client, codes[0]).status_code == 401
    assert _verify(client, codes[1]).status_code == 200


def test_backup_code_hashes_are_keyed_not_plain_sha256():
    code = "ABCDE-FGHIJ"
    assert hash_backup_code(code) != hashlib.sha256(code.encode()).hexdigest()


# --- H4: X-Forwarded-For only from trusted proxies -------------------------


def test_forwarded_for_is_ignored_unless_the_peer_is_a_trusted_proxy(monkeypatch):
    request = SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.9, 10.0.0.1"},
        client=SimpleNamespace(host="10.0.0.2"),
    )
    settings = get_settings()

    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "")
    assert get_client_ip(request) == "10.0.0.2"

    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "192.168.1.1")
    assert get_client_ip(request) == "10.0.0.2"

    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "10.0.0.2")
    assert get_client_ip(request) == "203.0.113.9"

    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "10.0.0.0/8")
    assert get_client_ip(request) == "203.0.113.9"


# --- H5: no account-existence oracles --------------------------------------


def test_unknown_email_and_wrong_password_are_indistinguishable(client):
    create_user(KNOWN_USER, role=SAFETY_OPERATOR_ROLE)

    unknown = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "Wrong-Passw0rd!"})
    wrong = client.post("/api/auth/login", json={"email": KNOWN_USER, "password": "Wrong-Passw0rd!"})

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()
    assert "remaining_attempts" not in wrong.json()["detail"]


def test_registering_an_existing_email_looks_like_a_new_request(client, tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "MAIL_TRANSPORT", "local")
    monkeypatch.setattr(settings, "MAIL_LOCAL_OUTBOX_DIR", str(tmp_path))
    body = {
        "full_name": "Dana Operator",
        "email": "dana@example.com",
        "role": SAFETY_OPERATOR_ROLE,
        "password": "Str0ng-Passw0rd!",
        "confirm_password": "Str0ng-Passw0rd!",
    }

    first = client.post("/api/auth/register", json=body)
    second = client.post("/api/auth/register", json=body)

    assert first.status_code == second.status_code == 202, (first.text, second.text)
    assert first.json() == second.json()
    assert "user" not in first.json()
    db = SessionLocal()
    try:
        assert db.query(User).filter(User.email == "dana@example.com").count() == 1
    finally:
        db.close()


def test_password_reset_request_is_identical_for_known_and_unknown_emails(client, tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "MAIL_TRANSPORT", "local")
    monkeypatch.setattr(settings, "MAIL_LOCAL_OUTBOX_DIR", str(tmp_path))
    create_user(KNOWN_USER, role=SAFETY_OPERATOR_ROLE)

    known = client.post("/api/auth/password-reset/request", json={"email": KNOWN_USER})
    unknown = client.post("/api/auth/password-reset/request", json={"email": "nobody@example.com"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert set(known.json()) == {"message"}
    assert list(tmp_path.iterdir())  # the real account did get its email


# --- H8: user-controlled text in outbound HTML mail ------------------------


def test_approval_email_escapes_user_supplied_fields():
    user = User(
        full_name='<img src=x onerror="steal()">Bob',
        email="bob@example.com",
        role=SAFETY_OPERATOR_ROLE,
        role_department="Safety Operator",
    )
    html = _build_approval_email_html(user=user, approve_url="https://x/a", reject_url="https://x/r")
    assert "<img" not in html
    assert "&lt;img src=x onerror=&quot;steal()&quot;&gt;Bob" in html


# --- N2: infrastructure failures are not "session expired" -----------------


def test_database_failure_in_the_auth_middleware_is_503_not_401(client, monkeypatch):
    def boom(_db, _token):
        raise RuntimeError("database is locked")

    monkeypatch.setattr("app.middleware.auth.get_user_by_access_token", boom)

    response = client.get("/api/auth/me", cookies={ACCESS_COOKIE: "anything"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Service unavailable."}
