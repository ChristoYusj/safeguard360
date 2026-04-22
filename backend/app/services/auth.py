"""
Authentication services and helpers.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta
import base64
import hashlib
import hmac
import io
import json
import math
import re
import secrets
from threading import Lock
from typing import Any

import bcrypt
import jwt
import pyotp
import qrcode
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.db.models import User
from app.services.audit import (
    AUDIT_ACCOUNT_APPROVED,
    AUDIT_ACCOUNT_REJECTED,
    AUDIT_LOGIN_FAILURE,
    AUDIT_LOGIN_SUCCESS,
    AUDIT_LOGOUT,
    AUDIT_PASSWORD_CHANGE,
    AUDIT_TWO_FACTOR_DISABLED,
    AUDIT_TWO_FACTOR_ENABLED,
    record_audit_event,
)
from app.services.email import send_email_via_resend
from app.services.rbac import (
    ADMIN_ROLE,
    ALL_USER_STATUSES,
    SELF_SERVICE_REGISTRATION_ROLES,
    USER_STATUS_ACTIVE,
    USER_STATUS_PENDING,
    USER_STATUS_REJECTED,
    USER_STATUS_RESTRICTED,
    derive_legacy_role,
    get_role_label,
    is_valid_self_service_role,
    is_valid_user_role,
)


ACCESS_COOKIE_NAME = "safeguard360_access"
REFRESH_COOKIE_NAME = "safeguard360_refresh"
PENDING_2FA_COOKIE_NAME = "safeguard360_2fa_pending"
SETUP_2FA_COOKIE_NAME = "safeguard360_2fa_setup"
LOGIN_FAILURE_MESSAGE = "Unable to sign in with those credentials."
LOCKOUT_MESSAGE = "Too many failed sign-in attempts. Try again later."
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
APPROVAL_TOKEN_HOURS = 48
PASSWORD_RESET_TOKEN_MINUTES = 15
PENDING_2FA_TOKEN_MINUTES = 10
SETUP_2FA_TOKEN_MINUTES = 10
BACKUP_CODE_COUNT = 8
PASSWORD_HAS_UPPERCASE = re.compile(r"[A-Z]")
PASSWORD_HAS_NUMBER = re.compile(r"\d")
PASSWORD_HAS_SPECIAL = re.compile(r"[^A-Za-z0-9]")

_IP_FAILURES: dict[str, deque[datetime]] = defaultdict(deque)
_IP_FAILURES_LOCK = Lock()


def utcnow() -> datetime:
    return datetime.utcnow()


def sanitize_text(value: str | None, max_length: int = 255) -> str:
    return (value or "").strip()[:max_length]


def normalize_email(email: str | None) -> str:
    return sanitize_text(email, max_length=255).lower()


def validate_email(email: str) -> bool:
    return bool(email and EMAIL_PATTERN.match(email))


def validate_password(password: str | None) -> bool:
    return bool(password and len(password) <= 4096)


def validate_registration_password(password: str) -> bool:
    return (
        len(password) >= 8
        and bool(PASSWORD_HAS_UPPERCASE.search(password))
        and bool(PASSWORD_HAS_NUMBER.search(password))
        and bool(PASSWORD_HAS_SPECIAL.search(password))
    )


def hash_password(password: str) -> str:
    settings = get_settings()
    password_bytes = password.encode("utf-8")
    hashed = bcrypt.hashpw(
        password_bytes,
        bcrypt.gensalt(rounds=settings.BCRYPT_SALT_ROUNDS),
    )
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        return False


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_backup_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _prune_ip_attempts(ip_address: str, now: datetime) -> deque[datetime]:
    settings = get_settings()
    attempts = _IP_FAILURES[ip_address]
    cutoff = now - timedelta(minutes=settings.AUTH_FAILED_LOGIN_WINDOW_MINUTES)
    while attempts and attempts[0] < cutoff:
        attempts.popleft()
    return attempts


def is_ip_rate_limited(ip_address: str) -> bool:
    if not ip_address:
        return False

    with _IP_FAILURES_LOCK:
        attempts = _prune_ip_attempts(ip_address, utcnow())
        return len(attempts) >= get_settings().AUTH_MAX_FAILED_IP_ATTEMPTS


def record_ip_failure(ip_address: str) -> None:
    if not ip_address:
        return

    with _IP_FAILURES_LOCK:
        attempts = _prune_ip_attempts(ip_address, utcnow())
        attempts.append(utcnow())


def clear_ip_failures(ip_address: str) -> None:
    if not ip_address:
        return

    with _IP_FAILURES_LOCK:
        _IP_FAILURES.pop(ip_address, None)


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _reset_failed_login_state(user: User) -> None:
    user.failed_login_attempts = 0
    user.last_failed_login_at = None
    user.lockout_until = None


def _record_user_failure(user: User) -> None:
    settings = get_settings()
    now = utcnow()
    window = timedelta(minutes=settings.AUTH_FAILED_LOGIN_WINDOW_MINUTES)

    if not user.last_failed_login_at or user.last_failed_login_at < now - window:
        user.failed_login_attempts = 0

    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    user.last_failed_login_at = now

    if user.failed_login_attempts >= settings.AUTH_MAX_FAILED_LOGIN_ATTEMPTS:
        user.lockout_until = now + timedelta(minutes=settings.AUTH_LOCKOUT_MINUTES)


def is_user_locked(user: User) -> bool:
    return bool(user.lockout_until and user.lockout_until > utcnow())


def get_remaining_login_attempts(user: User) -> int:
    max_attempts = get_settings().AUTH_MAX_FAILED_LOGIN_ATTEMPTS
    return max(0, max_attempts - int(user.failed_login_attempts or 0))


def get_lockout_retry_minutes(lockout_until: datetime | None) -> int:
    if not lockout_until:
        return max(1, int(get_settings().AUTH_LOCKOUT_MINUTES))
    remaining_seconds = max(0, (lockout_until - utcnow()).total_seconds())
    return max(1, int(math.ceil(remaining_seconds / 60)))


def build_login_error_detail(
    *,
    message: str,
    remaining_attempts: int | None = None,
    warning_message: str | None = None,
    is_locked: bool = False,
    retry_after_minutes: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "message": message,
        "is_locked": bool(is_locked),
    }
    if remaining_attempts is not None:
        payload["remaining_attempts"] = remaining_attempts
    if warning_message:
        payload["warning_message"] = warning_message
    if retry_after_minutes is not None:
        payload["retry_after_minutes"] = retry_after_minutes
    return payload


def ensure_login_request_is_valid(email: str, password: str) -> tuple[str, str]:
    normalized_email = normalize_email(email)
    password_value = password or ""

    if not validate_email(normalized_email) or not validate_password(password_value):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=build_login_error_detail(message=LOGIN_FAILURE_MESSAGE),
        )

    return normalized_email, password_value


def build_token_payload(user: User, token_type: str, expires_delta: timedelta) -> dict[str, Any]:
    issued_at = utcnow()
    expires_at = issued_at + expires_delta
    return {
        "jti": secrets.token_urlsafe(16),
        "sub": user.id,
        "email": user.email,
        "role": derive_legacy_role(user.role or user.role_department, user.email),
        "type": token_type,
        "status": user.status,
        "iat": issued_at,
        "exp": expires_at,
    }


def build_approval_token_payload(user: User, action: str) -> dict[str, Any]:
    issued_at = utcnow()
    expires_at = issued_at + timedelta(hours=APPROVAL_TOKEN_HOURS)
    return {
        "jti": secrets.token_urlsafe(16),
        "sub": user.id,
        "email": user.email,
        "type": "approval",
        "action": action,
        "status": user.status,
        "approval_version": user.approval_token_version or 0,
        "iat": issued_at,
        "exp": expires_at,
    }


def build_password_reset_token_payload(user: User) -> dict[str, Any]:
    issued_at = utcnow()
    expires_at = issued_at + timedelta(minutes=PASSWORD_RESET_TOKEN_MINUTES)
    return {
        "jti": secrets.token_urlsafe(16),
        "sub": user.id,
        "email": user.email,
        "type": "password_reset",
        "reset_version": user.password_reset_token_version or 0,
        "iat": issued_at,
        "exp": expires_at,
    }


def build_two_factor_token_payload(
    *,
    user_id: str,
    email: str,
    token_type: str,
    expires_delta: timedelta,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issued_at = utcnow()
    expires_at = issued_at + expires_delta
    payload = {
        "sub": user_id,
        "email": email,
        "type": token_type,
        "iat": issued_at,
        "exp": expires_at,
    }
    if extra:
        payload.update(extra)
    return payload


def create_access_token(user: User) -> str:
    settings = get_settings()
    payload = build_token_payload(
        user,
        token_type="access",
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES),
    )
    return jwt.encode(payload, settings.JWT_ACCESS_SECRET, algorithm="HS256")


def create_refresh_token(user: User) -> str:
    settings = get_settings()
    payload = build_token_payload(
        user,
        token_type="refresh",
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
    )
    return jwt.encode(payload, settings.JWT_REFRESH_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.JWT_ACCESS_SECRET, algorithms=["HS256"])


def decode_refresh_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.JWT_REFRESH_SECRET, algorithms=["HS256"])


def create_approval_token(user: User, action: str) -> str:
    settings = get_settings()
    payload = build_approval_token_payload(user, action=action)
    return jwt.encode(payload, settings.JWT_APPROVAL_SECRET, algorithm="HS256")


def decode_approval_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.JWT_APPROVAL_SECRET, algorithms=["HS256"])


def create_password_reset_token(user: User) -> str:
    settings = get_settings()
    payload = build_password_reset_token_payload(user)
    return jwt.encode(payload, settings.JWT_APPROVAL_SECRET, algorithm="HS256")


def decode_password_reset_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.JWT_APPROVAL_SECRET, algorithms=["HS256"])


def create_pending_two_factor_token(user: User) -> str:
    settings = get_settings()
    payload = build_two_factor_token_payload(
        user_id=user.id,
        email=user.email,
        token_type="pending_2fa",
        expires_delta=timedelta(minutes=PENDING_2FA_TOKEN_MINUTES),
    )
    return jwt.encode(payload, settings.JWT_ACCESS_SECRET, algorithm="HS256")


def decode_pending_two_factor_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.JWT_ACCESS_SECRET, algorithms=["HS256"])


def create_two_factor_setup_token(user: User, secret: str) -> str:
    settings = get_settings()
    payload = build_two_factor_token_payload(
        user_id=user.id,
        email=user.email,
        token_type="setup_2fa",
        expires_delta=timedelta(minutes=SETUP_2FA_TOKEN_MINUTES),
        extra={"secret": encrypt_totp_secret(secret)},
    )
    return jwt.encode(payload, settings.JWT_ACCESS_SECRET, algorithm="HS256")


def decode_two_factor_setup_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.JWT_ACCESS_SECRET, algorithms=["HS256"])


def store_refresh_token(user: User, refresh_token: str) -> None:
    user.refresh_token = hash_refresh_token(refresh_token)


def verify_stored_refresh_token(user: User, refresh_token: str) -> bool:
    if not user.refresh_token:
        return False
    return hmac.compare_digest(user.refresh_token, hash_refresh_token(refresh_token))


def clear_refresh_token(user: User) -> None:
    user.refresh_token = None


def serialize_user(user: User) -> dict[str, Any]:
    role = derive_legacy_role(user.role or user.role_department, user.email)
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": role,
        "role_label": get_role_label(role),
        "role_department": user.role_department,
        "status": user.status,
        "two_factor_enabled": bool(user.two_factor_enabled),
    }


def _build_approval_email_html(
    *,
    user: User,
    approve_url: str,
    reject_url: str,
) -> str:
    role = derive_legacy_role(user.role or user.role_department, user.email)
    return f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #111827;">
      <h2>New operator registration request</h2>
      <p>A new operator requested access to SafeGuard 360.</p>
      <ul>
        <li><strong>Name:</strong> {user.full_name}</li>
        <li><strong>Email:</strong> {user.email}</li>
        <li><strong>Requested Role:</strong> {get_role_label(role)}</li>
      </ul>
      <p>Choose whether to approve or reject this request.</p>
      <p>
        <a href="{approve_url}" style="display:inline-block;margin-right:12px;padding:12px 18px;background:#0ea5e9;color:#ffffff;text-decoration:none;border-radius:8px;">Approve</a>
        <a href="{reject_url}" style="display:inline-block;padding:12px 18px;background:#ef4444;color:#ffffff;text-decoration:none;border-radius:8px;">Reject</a>
      </p>
      <p>These links expire in {APPROVAL_TOKEN_HOURS} hours.</p>
    </div>
    """


def _build_password_reset_email_html(*, full_name: str, reset_url: str) -> str:
    return f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #111827;">
      <h2>Reset your SafeGuard 360 password</h2>
      <p>Hello {full_name},</p>
      <p>Use the link below to choose a new password for your operator account.</p>
      <p>
        <a href="{reset_url}" style="display:inline-block;padding:12px 18px;background:#0ea5e9;color:#ffffff;text-decoration:none;border-radius:8px;">Reset password</a>
      </p>
      <p>This link expires in {PASSWORD_RESET_TOKEN_MINUTES} minutes and can only be used once.</p>
      <p>If you did not request a password reset, you can ignore this email.</p>
    </div>
    """


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    settings = get_settings()
    common_kwargs = {
        "httponly": True,
        "secure": bool(settings.COOKIE_SECURE),
        "samesite": "strict",
        "path": "/",
    }
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        access_token,
        max_age=settings.ACCESS_TOKEN_TTL_MINUTES * 60,
        **common_kwargs,
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=settings.REFRESH_TOKEN_TTL_DAYS * 24 * 60 * 60,
        **common_kwargs,
    )


def set_pending_two_factor_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        PENDING_2FA_COOKIE_NAME,
        token,
        max_age=PENDING_2FA_TOKEN_MINUTES * 60,
        httponly=True,
        secure=bool(settings.COOKIE_SECURE),
        samesite="strict",
        path="/",
    )


def set_two_factor_setup_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SETUP_2FA_COOKIE_NAME,
        token,
        max_age=SETUP_2FA_TOKEN_MINUTES * 60,
        httponly=True,
        secure=bool(settings.COOKIE_SECURE),
        samesite="strict",
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    for cookie_name in (
        ACCESS_COOKIE_NAME,
        REFRESH_COOKIE_NAME,
        PENDING_2FA_COOKIE_NAME,
        SETUP_2FA_COOKIE_NAME,
    ):
        response.delete_cookie(
            cookie_name,
            path="/",
            samesite="strict",
            secure=bool(settings.COOKIE_SECURE),
            httponly=True,
        )


def clear_two_factor_setup_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        SETUP_2FA_COOKIE_NAME,
        path="/",
        samesite="strict",
        secure=bool(settings.COOKIE_SECURE),
        httponly=True,
    )


def clear_pending_two_factor_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        PENDING_2FA_COOKIE_NAME,
        path="/",
        samesite="strict",
        secure=bool(settings.COOKIE_SECURE),
        httponly=True,
    )


def _get_fernet() -> Fernet:
    raw_key = get_settings().TOTP_ENCRYPTION_KEY
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Two-factor encryption is not configured.",
        )
    derived_key = base64.urlsafe_b64encode(hashlib.sha256(raw_key.encode("utf-8")).digest())
    return Fernet(derived_key)


def encrypt_totp_secret(secret: str) -> str:
    encrypted = _get_fernet().encrypt(secret.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_totp_secret(encrypted_secret: str | None) -> str:
    if not encrypted_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is not configured for this account.",
        )
    try:
        decrypted = _get_fernet().decrypt(encrypted_secret.encode("utf-8"))
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored two-factor configuration could not be read.",
        ) from exc
    return decrypted.decode("utf-8")


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def build_totp_provisioning_uri(user: User, secret: str) -> str:
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=user.email, issuer_name="SafeGuard 360")


def generate_qr_code_data_url(data: str) -> str:
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def verify_totp_code(secret: str, code: str) -> bool:
    normalized = sanitize_text(code, max_length=32).replace(" ", "")
    return pyotp.TOTP(secret).verify(normalized, valid_window=1)


def generate_backup_codes() -> tuple[list[str], str]:
    plain_codes = []
    hashed_codes = []
    for _ in range(BACKUP_CODE_COUNT):
        raw = secrets.token_hex(4).upper()
        formatted = f"{raw[:4]}-{raw[4:]}"
        plain_codes.append(formatted)
        hashed_codes.append(hash_backup_code(formatted))
    return plain_codes, json.dumps(hashed_codes)


def parse_backup_codes(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return [str(entry) for entry in parsed if entry]
    return []


def consume_backup_code(user: User, submitted_code: str) -> bool:
    normalized = sanitize_text(submitted_code, max_length=32).upper()
    if not normalized:
        return False
    hashed_codes = parse_backup_codes(user.backup_codes)
    hashed_value = hash_backup_code(normalized)
    if hashed_value not in hashed_codes:
        return False
    hashed_codes.remove(hashed_value)
    user.backup_codes = json.dumps(hashed_codes)
    return True


def seed_bootstrap_operator(db: Session) -> None:
    settings = get_settings()
    if not settings.bootstrap_admin_enabled:
        return

    admin_email = normalize_email(settings.ADMIN_EMAIL)
    if not validate_email(admin_email):
        return

    existing_user = db.query(User).filter(User.email == admin_email).first()
    if existing_user:
        return

    bootstrap_password = sanitize_text(settings.BOOTSTRAP_ADMIN_PASSWORD, max_length=4096)
    if not bootstrap_password:
        return

    db.add(
        User(
            full_name=sanitize_text(settings.BOOTSTRAP_ADMIN_NAME, max_length=150)
            or "System Administrator",
            email=admin_email,
            role_department="Admin",
            role=ADMIN_ROLE,
            password_hash=hash_password(bootstrap_password),
            status=USER_STATUS_ACTIVE,
            two_factor_enabled=False,
        )
    )


def backfill_user_roles(db: Session) -> None:
    users = db.query(User).all()
    for user in users:
        normalized_role = derive_legacy_role(user.role or user.role_department, user.email)
        normalized_status = (user.status or "").strip().lower()
        dirty = False

        if user.role != normalized_role:
            user.role = normalized_role
            dirty = True

        if user.email and user.email.strip().lower() == (get_settings().ADMIN_EMAIL or "").strip().lower():
            if user.role_department != "Admin":
                user.role_department = "Admin"
                dirty = True

        if normalized_status not in ALL_USER_STATUSES:
            user.status = USER_STATUS_ACTIVE
            dirty = True

        if user.approval_token_version is None:
            user.approval_token_version = 0
            dirty = True

        if user.password_reset_token_version is None:
            user.password_reset_token_version = 0
            dirty = True

        if dirty:
            db.add(user)


def build_public_app_base_url(request: Request) -> str:
    configured_url = sanitize_text(get_settings().FRONTEND_APP_URL, max_length=2048)
    if configured_url:
        return configured_url.rstrip("/")

    origin = sanitize_text(request.headers.get("origin"), max_length=2048)
    if origin:
        return origin.rstrip("/")

    referer = sanitize_text(request.headers.get("referer"), max_length=2048)
    if referer:
        trimmed = referer.split("#", 1)[0].split("?", 1)[0].rstrip("/")
        if trimmed:
            return trimmed.rsplit("/", 1)[0] if "/auth/" in trimmed else trimmed

    return str(request.base_url).rstrip("/")


def build_approval_urls(request: Request, user: User) -> tuple[str, str]:
    approve_token = create_approval_token(user, "approve")
    reject_token = create_approval_token(user, "reject")
    base_url = str(request.base_url).rstrip("/")
    return (
        f"{base_url}/api/auth/approval/approve?token={approve_token}",
        f"{base_url}/api/auth/approval/reject?token={reject_token}",
    )


def build_password_reset_url(request: Request, user: User) -> str:
    reset_token = create_password_reset_token(user)
    app_base_url = build_public_app_base_url(request)
    return f"{app_base_url}/auth/reset-password?token={reset_token}"


def register_pending_operator(
    db: Session,
    request: Request,
    *,
    full_name: str,
    email: str,
    role: str,
    password: str,
) -> User:
    normalized_email = normalize_email(email)
    clean_name = sanitize_text(full_name, max_length=150)
    clean_role = derive_legacy_role(role, normalized_email)

    if not clean_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Full name is required.")
    if not validate_email(normalized_email):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A valid email is required.")
    if not is_valid_self_service_role(clean_role):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A valid operator role is required.",
        )
    if not validate_registration_password(password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters and include an uppercase letter, number, and special character.",
        )

    existing_user = db.query(User).filter(User.email == normalized_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account request already exists for that email.",
        )

    pending_user = User(
        full_name=clean_name,
        email=normalized_email,
        role_department=get_role_label(clean_role),
        role=clean_role,
        password_hash=hash_password(password),
        status=USER_STATUS_PENDING,
        approval_token_version=0,
        two_factor_enabled=False,
    )
    db.add(pending_user)
    db.commit()
    db.refresh(pending_user)

    try:
        approve_url, reject_url = build_approval_urls(request, pending_user)
        send_email_via_resend(
            to_email=get_settings().ADMIN_EMAIL,
            subject="SafeGuard 360 operator approval required",
            html=_build_approval_email_html(
                user=pending_user,
                approve_url=approve_url,
                reject_url=reject_url,
            ),
        )
    except Exception:
        db.delete(pending_user)
        db.commit()
        raise

    return pending_user


def request_password_reset(
    db: Session,
    request: Request,
    *,
    email: str,
) -> None:
    normalized_email = normalize_email(email)
    if not validate_email(normalized_email):
        return

    user = db.query(User).filter(User.email == normalized_email).first()
    if not user or user.status not in {USER_STATUS_ACTIVE, USER_STATUS_RESTRICTED}:
        return

    reset_url = build_password_reset_url(request, user)
    send_email_via_resend(
        to_email=user.email,
        subject="SafeGuard 360 password reset",
        html=_build_password_reset_email_html(
            full_name=user.full_name,
            reset_url=reset_url,
        ),
    )


def reset_password_with_token(
    db: Session,
    *,
    token: str,
    password: str,
    ip_address: str | None = None,
) -> None:
    if not validate_registration_password(password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters and include an uppercase letter, number, and special character.",
        )

    try:
        payload = decode_password_reset_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This password reset link is invalid or expired.",
        ) from exc

    if payload.get("type") != "password_reset":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This password reset link is invalid or expired.",
        )

    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This password reset link is invalid or expired.",
        )

    if payload.get("reset_version") != (user.password_reset_token_version or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This password reset link is invalid or expired.",
        )

    if user.status not in {USER_STATUS_ACTIVE, USER_STATUS_RESTRICTED}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This password reset link is invalid or expired.",
        )

    user.password_hash = hash_password(password)
    user.password_reset_token_version = (user.password_reset_token_version or 0) + 1
    user.refresh_token = None
    _reset_failed_login_state(user)
    record_audit_event(
        db,
        operator_email=user.email,
        event_type=AUDIT_PASSWORD_CHANGE,
        ip_address=ip_address,
        detail="Password reset completed via emailed reset link.",
    )
    db.add(user)
    db.commit()


def change_password_for_user(
    db: Session,
    *,
    user: User,
    current_password: str,
    new_password: str,
    ip_address: str | None = None,
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect.",
        )

    if not validate_registration_password(new_password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters and include an uppercase letter, number, and special character.",
        )

    if verify_password(new_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Choose a new password that is different from the current one.",
        )

    user.password_hash = hash_password(new_password)
    user.password_reset_token_version = (user.password_reset_token_version or 0) + 1
    _reset_failed_login_state(user)
    record_audit_event(
        db,
        operator_email=user.email,
        event_type=AUDIT_PASSWORD_CHANGE,
        ip_address=ip_address,
        detail="Password changed from authenticated settings.",
    )
    db.add(user)
    db.commit()
    db.refresh(user)


def resolve_registration_decision(
    db: Session,
    *,
    token: str,
    expected_action: str,
    ip_address: str | None = None,
) -> tuple[User, str]:
    try:
        payload = decode_approval_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This approval link is invalid or expired.",
        ) from exc

    if payload.get("type") != "approval" or payload.get("action") != expected_action:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This approval link is invalid or expired.",
        )

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested account was not found.",
        )

    if payload.get("approval_version") != (user.approval_token_version or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This approval link is invalid or expired.",
        )

    if user.status != USER_STATUS_PENDING:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This approval link is invalid or expired.",
        )

    user.status = USER_STATUS_ACTIVE if expected_action == "approve" else USER_STATUS_REJECTED
    user.approval_token_version = (user.approval_token_version or 0) + 1
    record_audit_event(
        db,
        operator_email=user.email,
        event_type=AUDIT_ACCOUNT_APPROVED if expected_action == "approve" else AUDIT_ACCOUNT_REJECTED,
        ip_address=ip_address,
        detail=(
            "Account approved via signed email link."
            if expected_action == "approve"
            else "Account rejected via signed email link."
        ),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return user, (
        "Your SafeGuard 360 account was approved. You can now sign in."
        if user.status == USER_STATUS_ACTIVE
        else "Your SafeGuard 360 account request was not approved."
    )


def verify_operator_credentials(
    db: Session,
    request: Request,
    email: str,
    password: str,
) -> User:
    ip_address = get_client_ip(request)
    try:
        normalized_email, password_value = ensure_login_request_is_valid(email, password)
    except HTTPException:
        record_audit_event(
            db,
            operator_email=normalize_email(email),
            event_type=AUDIT_LOGIN_FAILURE,
            ip_address=ip_address,
            detail="Login failed because the submitted credentials were malformed.",
            commit=True,
        )
        raise

    user = db.query(User).filter(User.email == normalized_email).first()
    if not user:
        if is_ip_rate_limited(ip_address):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=build_login_error_detail(
                    message=LOCKOUT_MESSAGE,
                    is_locked=True,
                    retry_after_minutes=get_settings().AUTH_LOCKOUT_MINUTES,
                ),
            )
        record_ip_failure(ip_address)
        record_audit_event(
            db,
            operator_email=normalized_email,
            event_type=AUDIT_LOGIN_FAILURE,
            ip_address=ip_address,
            detail="Login failed because the credentials were invalid.",
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=build_login_error_detail(message=LOGIN_FAILURE_MESSAGE),
        )

    if user and is_user_locked(user):
        retry_after_minutes = get_lockout_retry_minutes(user.lockout_until)
        record_audit_event(
            db,
            operator_email=user.email,
            event_type=AUDIT_LOGIN_FAILURE,
            ip_address=ip_address,
            detail="Login denied because the account is locked.",
        )
        db.add(user)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=build_login_error_detail(
                message=f"Too many failed sign-in attempts. Try again in {retry_after_minutes} minute{'s' if retry_after_minutes != 1 else ''}.",
                is_locked=True,
                retry_after_minutes=retry_after_minutes,
                remaining_attempts=0,
            ),
        )

    if not verify_password(password_value, user.password_hash):
        _record_user_failure(user)
        remaining_attempts = get_remaining_login_attempts(user)
        is_locked = is_user_locked(user)
        retry_after_minutes = get_lockout_retry_minutes(user.lockout_until) if is_locked else None
        warning_message = None
        if not is_locked and remaining_attempts in {1, 2}:
            warning_message = (
                f"{remaining_attempts} attempt{'s' if remaining_attempts != 1 else ''} remaining before your account is locked"
            )
        record_audit_event(
            db,
            operator_email=user.email,
            event_type=AUDIT_LOGIN_FAILURE,
            ip_address=ip_address,
            detail="Login failed because the password was invalid.",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        record_ip_failure(ip_address)
        if is_locked:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=build_login_error_detail(
                    message=f"Too many failed sign-in attempts. Try again in {retry_after_minutes} minute{'s' if retry_after_minutes != 1 else ''}.",
                    is_locked=True,
                    retry_after_minutes=retry_after_minutes,
                    remaining_attempts=0,
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=build_login_error_detail(
                message=LOGIN_FAILURE_MESSAGE,
                remaining_attempts=remaining_attempts,
                warning_message=warning_message,
            ),
        )

    if user.status == USER_STATUS_PENDING:
        record_audit_event(
            db,
            operator_email=user.email,
            event_type=AUDIT_LOGIN_FAILURE,
            ip_address=ip_address,
            detail="Login denied because the account is pending approval.",
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is pending approval.",
        )

    if user.status == USER_STATUS_REJECTED:
        record_audit_event(
            db,
            operator_email=user.email,
            event_type=AUDIT_LOGIN_FAILURE,
            ip_address=ip_address,
            detail="Login denied because the account was rejected.",
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account was not approved.",
        )

    if user.status == USER_STATUS_RESTRICTED:
        record_audit_event(
            db,
            operator_email=user.email,
            event_type=AUDIT_LOGIN_FAILURE,
            ip_address=ip_address,
            detail="Login denied because the account is deactivated.",
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is deactivated.",
        )

    if user.status != USER_STATUS_ACTIVE:
        record_audit_event(
            db,
            operator_email=user.email,
            event_type=AUDIT_LOGIN_FAILURE,
            ip_address=ip_address,
            detail="Login denied because the account is not active.",
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=LOGIN_FAILURE_MESSAGE,
        )

    _reset_failed_login_state(user)
    db.add(user)
    db.commit()
    clear_ip_failures(ip_address)
    db.refresh(user)
    return user


def authenticate_operator(
    db: Session,
    request: Request,
    email: str,
    password: str,
) -> User:
    user = verify_operator_credentials(
        db=db,
        request=request,
        email=email,
        password=password,
    )

    if user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Two-factor verification is required for this account.",
        )

    return user


def issue_login_tokens(db: Session, user: User) -> tuple[str, str]:
    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user)
    store_refresh_token(user, refresh_token)
    db.add(user)
    db.commit()
    db.refresh(user)
    return access_token, refresh_token


def record_login_success(db: Session, user: User, ip_address: str | None, *, detail: str | None = None) -> None:
    record_audit_event(
        db,
        operator_email=user.email,
        event_type=AUDIT_LOGIN_SUCCESS,
        ip_address=ip_address,
        detail=detail or "Operator signed in successfully.",
    )
    db.commit()
    db.refresh(user)


def create_two_factor_setup_payload(user: User) -> tuple[str, str, str]:
    if user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Two-factor authentication is already enabled.",
        )
    secret = generate_totp_secret()
    otpauth_url = build_totp_provisioning_uri(user, secret)
    qr_code_data_url = generate_qr_code_data_url(otpauth_url)
    setup_token = create_two_factor_setup_token(user, secret)
    return setup_token, otpauth_url, qr_code_data_url


def resolve_pending_two_factor_user(db: Session, token: str | None) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Two-factor verification session expired.",
        )
    try:
        payload = decode_pending_two_factor_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Two-factor verification session expired.",
        ) from exc

    if payload.get("type") != "pending_2fa":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Two-factor verification session expired.",
        )

    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user or user.status != USER_STATUS_ACTIVE or not user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Two-factor verification session expired.",
        )
    return user


def verify_two_factor_for_login(
    db: Session,
    *,
    token: str | None,
    code: str,
) -> User:
    user = resolve_pending_two_factor_user(db, token)
    secret = decrypt_totp_secret(user.two_factor_secret)
    normalized_code = sanitize_text(code, max_length=32).upper().replace(" ", "")
    totp_valid = verify_totp_code(secret, normalized_code)
    backup_valid = False
    if not totp_valid:
        backup_valid = consume_backup_code(user, normalized_code)
    if not totp_valid and not backup_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication code.",
        )
    if backup_valid:
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def resolve_two_factor_setup_secret(token: str | None, user: User) -> str:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Two-factor setup session expired.",
        )
    try:
        payload = decode_two_factor_setup_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Two-factor setup session expired.",
        ) from exc
    if payload.get("type") != "setup_2fa" or payload.get("sub") != user.id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Two-factor setup session expired.",
        )
    secret = payload.get("secret")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Two-factor setup session expired.",
        )
    try:
        return decrypt_totp_secret(secret)
    except HTTPException as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Two-factor setup session expired.",
        ) from exc


def enable_two_factor(
    db: Session,
    *,
    user: User,
    setup_token: str | None,
    code: str,
    ip_address: str | None,
) -> list[str]:
    if user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Two-factor authentication is already enabled.",
        )
    secret = resolve_two_factor_setup_secret(setup_token, user)
    if not verify_totp_code(secret, code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication code.",
        )
    backup_codes, stored_codes = generate_backup_codes()
    user.two_factor_secret = encrypt_totp_secret(secret)
    user.two_factor_enabled = True
    user.backup_codes = stored_codes
    record_audit_event(
        db,
        operator_email=user.email,
        event_type=AUDIT_TWO_FACTOR_ENABLED,
        ip_address=ip_address,
        detail="Two-factor authentication was enabled.",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return backup_codes


def disable_two_factor(
    db: Session,
    *,
    user: User,
    current_password: str,
    code: str,
    ip_address: str | None,
) -> None:
    if not user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Two-factor authentication is already disabled.",
        )
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect.",
        )
    secret = decrypt_totp_secret(user.two_factor_secret)
    normalized_code = sanitize_text(code, max_length=32).upper().replace(" ", "")
    if not verify_totp_code(secret, normalized_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication code.",
        )
    user.two_factor_secret = None
    user.two_factor_enabled = False
    user.backup_codes = None
    record_audit_event(
        db,
        operator_email=user.email,
        event_type=AUDIT_TWO_FACTOR_DISABLED,
        ip_address=ip_address,
        detail="Two-factor authentication was disabled.",
    )
    db.add(user)
    db.commit()


def get_user_by_access_token(db: Session, token: str | None) -> tuple[User, dict[str, Any]]:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        ) from exc

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.status != USER_STATUS_ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    return user, payload


def get_user_by_refresh_token(db: Session, token: str | None) -> tuple[User, dict[str, Any]]:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        payload = decode_refresh_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        ) from exc

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.status != USER_STATUS_ACTIVE or not verify_stored_refresh_token(user, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    return user, payload
