"""
Authentication services and helpers.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta
import hashlib
import hmac
import re
from threading import Lock
from typing import Any

import bcrypt
import jwt
from fastapi import HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.db.models import User


ACCESS_COOKIE_NAME = "safeguard360_access"
REFRESH_COOKIE_NAME = "safeguard360_refresh"
LOGIN_FAILURE_MESSAGE = "Unable to sign in with those credentials."
LOCKOUT_MESSAGE = "Too many failed sign-in attempts. Try again later."
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

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


def ensure_login_request_is_valid(email: str, password: str) -> tuple[str, str]:
    normalized_email = normalize_email(email)
    password_value = password or ""

    if not validate_email(normalized_email) or not validate_password(password_value):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=LOGIN_FAILURE_MESSAGE,
        )

    return normalized_email, password_value


def build_token_payload(user: User, token_type: str, expires_delta: timedelta) -> dict[str, Any]:
    issued_at = utcnow()
    expires_at = issued_at + expires_delta
    return {
        "sub": user.id,
        "email": user.email,
        "type": token_type,
        "status": user.status,
        "iat": issued_at,
        "exp": expires_at,
    }


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


def store_refresh_token(user: User, refresh_token: str) -> None:
    user.refresh_token = hash_refresh_token(refresh_token)


def verify_stored_refresh_token(user: User, refresh_token: str) -> bool:
    if not user.refresh_token:
        return False
    return hmac.compare_digest(user.refresh_token, hash_refresh_token(refresh_token))


def clear_refresh_token(user: User) -> None:
    user.refresh_token = None


def serialize_user(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role_department": user.role_department,
        "status": user.status,
        "two_factor_enabled": bool(user.two_factor_enabled),
    }


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


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    for cookie_name in (ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME):
        response.delete_cookie(
            cookie_name,
            path="/",
            samesite="strict",
            secure=bool(settings.COOKIE_SECURE),
            httponly=True,
        )


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
            role_department=sanitize_text(settings.BOOTSTRAP_ADMIN_ROLE, max_length=150)
            or "Platform Manager",
            password_hash=hash_password(bootstrap_password),
            status="active",
            two_factor_enabled=False,
        )
    )


def authenticate_operator(
    db: Session,
    request: Request,
    email: str,
    password: str,
) -> User:
    normalized_email, password_value = ensure_login_request_is_valid(email, password)
    ip_address = get_client_ip(request)

    if is_ip_rate_limited(ip_address):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=LOCKOUT_MESSAGE)

    user = db.query(User).filter(User.email == normalized_email).first()
    if user and is_user_locked(user):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=LOCKOUT_MESSAGE)

    if not user or not verify_password(password_value, user.password_hash):
        if user:
            _record_user_failure(user)
            db.add(user)
            db.commit()
            db.refresh(user)
        record_ip_failure(ip_address)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=LOGIN_FAILURE_MESSAGE,
        )

    if user.status == "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is pending approval.",
        )

    if user.status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account was not approved.",
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=LOGIN_FAILURE_MESSAGE,
        )

    if user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Two-factor verification is required for this account.",
        )

    _reset_failed_login_state(user)
    db.add(user)
    db.commit()
    clear_ip_failures(ip_address)
    db.refresh(user)
    return user


def issue_login_tokens(db: Session, user: User) -> tuple[str, str]:
    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user)
    store_refresh_token(user, refresh_token)
    db.add(user)
    db.commit()
    db.refresh(user)
    return access_token, refresh_token


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
    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    return user, payload
