"""
Authentication routes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.db.models import User
from app.services.auth import (
    change_password_for_user,
    clear_pending_two_factor_cookie,
    clear_two_factor_setup_cookie,
    clear_auth_cookies,
    clear_refresh_token,
    create_pending_two_factor_token,
    create_two_factor_setup_payload,
    disable_two_factor,
    enable_two_factor,
    get_client_ip,
    issue_login_tokens,
    record_login_success,
    request_password_reset,
    register_pending_operator,
    reset_password_with_token,
    resolve_registration_decision,
    set_pending_two_factor_cookie,
    set_two_factor_setup_cookie,
    serialize_user,
    set_auth_cookies,
    REFRESH_COOKIE_NAME,
    get_user_by_refresh_token,
    verify_operator_credentials,
    verify_two_factor_for_login,
    SETUP_2FA_COOKIE_NAME,
    PENDING_2FA_COOKIE_NAME,
)
from app.services.audit import AUDIT_LOGOUT, record_audit_event
from app.services.rbac import (
    SELF_SERVICE_REGISTRATION_ROLES,
    get_role_label,
    is_valid_self_service_role,
)


router = APIRouter()


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str
    password: str


class RegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str
    email: str
    role: str
    password: str
    confirm_password: str

    @field_validator("full_name", "email", "role")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("This field is required.")
        return value

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if not is_valid_self_service_role(value):
            allowed = ", ".join(get_role_label(role) for role in sorted(SELF_SERVICE_REGISTRATION_ROLES))
            raise ValueError(f"Role must be one of: {allowed}.")
        return value

    @field_validator("confirm_password")
    @classmethod
    def validate_confirmation(cls, value: str, info) -> str:
        password = info.data.get("password")
        if password and value != password:
            raise ValueError("Passwords do not match.")
        return value


class TwoFactorCodeRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    code: str


class DisableTwoFactorRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    current_password: str
    code: str


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str


class PasswordResetConfirmRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    token: str
    password: str
    confirm_password: str

    @field_validator("confirm_password")
    @classmethod
    def validate_confirmation(cls, value: str, info) -> str:
        password = info.data.get("password")
        if password and value != password:
            raise ValueError("Passwords do not match.")
        return value


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    current_password: str
    password: str
    confirm_password: str

    @field_validator("confirm_password")
    @classmethod
    def validate_confirmation(cls, value: str, info) -> str:
        password = info.data.get("password")
        if password and value != password:
            raise ValueError("Passwords do not match.")
        return value


def _get_persistent_request_user(request: Request, db: Session) -> User:
    current_user = getattr(request.state, "user", None)
    if not isinstance(current_user, User):
        raise HTTPException(status_code=401, detail="Authentication required.")
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = verify_operator_credentials(
        db=db,
        request=request,
        email=payload.email,
        password=payload.password,
    )
    if user.two_factor_enabled:
        pending_token = create_pending_two_factor_token(user)
        response = JSONResponse(
            {"requires_two_factor": True},
            status_code=status.HTTP_202_ACCEPTED,
        )
        set_pending_two_factor_cookie(response, pending_token)
        return response
    access_token, refresh_token = issue_login_tokens(db, user)
    record_login_success(db, user, get_client_ip(request))
    response = JSONResponse({"user": serialize_user(user)})
    set_auth_cookies(response, access_token, refresh_token)
    return response


@router.post("/2fa/verify")
def verify_two_factor_login(
    payload: TwoFactorCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = verify_two_factor_for_login(
        db=db,
        token=request.cookies.get(PENDING_2FA_COOKIE_NAME),
        code=payload.code,
    )
    access_token, refresh_token = issue_login_tokens(db, user)
    record_login_success(
        db,
        user,
        get_client_ip(request),
        detail="Operator signed in successfully after two-factor verification.",
    )
    response = JSONResponse({"user": serialize_user(user)})
    set_auth_cookies(response, access_token, refresh_token)
    clear_pending_two_factor_cookie(response)
    return response


@router.post("/register", status_code=202)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    pending_user = register_pending_operator(
        db=db,
        request=request,
        full_name=payload.full_name,
        email=payload.email,
        role=payload.role,
        password=payload.password,
    )
    return {
        "message": "Your account request was submitted and is pending approval.",
        "user": serialize_user(pending_user),
    }


@router.post("/password-reset/request", status_code=202)
def request_operator_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    result = request_password_reset(
        db=db,
        request=request,
        email=payload.email,
    )
    response = {
        "message": "If the account exists, a password reset link has been sent.",
    }
    if result:
        response.update(result)
    return response


@router.post("/password-reset/confirm")
def confirm_operator_password_reset(
    payload: PasswordResetConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    reset_password_with_token(
        db=db,
        token=payload.token,
        password=payload.password,
        ip_address=get_client_ip(request),
    )
    return {
        "message": "Your password has been reset. You can now sign in.",
    }


@router.post("/password/change")
def change_operator_password(
    payload: PasswordChangeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _get_persistent_request_user(request, db)
    change_password_for_user(
        db=db,
        user=user,
        current_password=payload.current_password,
        new_password=payload.password,
        ip_address=get_client_ip(request),
    )
    refreshed_user = db.query(User).filter(User.id == user.id).first() or user
    access_token, refresh_token = issue_login_tokens(db, refreshed_user)
    response = JSONResponse(
        {
            "message": "Password updated successfully.",
            "user": serialize_user(refreshed_user),
        }
    )
    set_auth_cookies(response, access_token, refresh_token)
    return response


@router.get("/me")
def get_current_operator(request: Request):
    current_user = getattr(request.state, "user", None)
    if not current_user:
        return JSONResponse({"detail": "Authentication required."}, status_code=401)
    return {"user": serialize_user(current_user)}


@router.post("/refresh")
def refresh_operator_session(request: Request, db: Session = Depends(get_db)):
    user, _ = get_user_by_refresh_token(
        db,
        request.cookies.get(REFRESH_COOKIE_NAME),
    )
    access_token, refresh_token = issue_login_tokens(db, user)
    response = JSONResponse({"user": serialize_user(user)})
    set_auth_cookies(response, access_token, refresh_token)
    return response


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    current_user = getattr(request.state, "user", None)
    persistent_user = None
    if isinstance(current_user, User):
        persistent_user = db.query(User).filter(User.id == current_user.id).first()
    if not persistent_user:
        refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
        if refresh_token:
            try:
                persistent_user, _ = get_user_by_refresh_token(db, refresh_token)
            except HTTPException:
                persistent_user = None
    if persistent_user:
        clear_refresh_token(persistent_user)
        record_audit_event(
            db,
            operator_email=persistent_user.email,
            event_type=AUDIT_LOGOUT,
            ip_address=get_client_ip(request),
            detail="Operator signed out.",
        )
        db.add(persistent_user)
        db.commit()

    response = JSONResponse({"success": True})
    clear_auth_cookies(response)
    return response


@router.post("/2fa/setup")
def start_two_factor_setup(request: Request, db: Session = Depends(get_db)):
    user = _get_persistent_request_user(request, db)
    setup_token, otpauth_url, qr_code_data_url = create_two_factor_setup_payload(user)
    response = JSONResponse(
        {
            "otpauth_url": otpauth_url,
            "qr_code_data_url": qr_code_data_url,
        }
    )
    set_two_factor_setup_cookie(response, setup_token)
    return response


@router.post("/2fa/enable")
def confirm_two_factor_enable(
    payload: TwoFactorCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _get_persistent_request_user(request, db)
    backup_codes = enable_two_factor(
        db=db,
        user=user,
        setup_token=request.cookies.get(SETUP_2FA_COOKIE_NAME),
        code=payload.code,
        ip_address=get_client_ip(request),
    )
    response = JSONResponse(
        {
            "message": "Two-factor authentication is now enabled.",
            "backup_codes": backup_codes,
            "user": serialize_user(user),
        }
    )
    clear_two_factor_setup_cookie(response)
    return response


@router.post("/2fa/disable")
def disable_two_factor_auth(
    payload: DisableTwoFactorRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _get_persistent_request_user(request, db)
    disable_two_factor(
        db=db,
        user=user,
        current_password=payload.current_password,
        code=payload.code,
        ip_address=get_client_ip(request),
    )
    return {
        "message": "Two-factor authentication was disabled.",
        "user": serialize_user(user),
    }


@router.get("/approval/approve", response_class=HTMLResponse)
def approve_registration(
    request: Request,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    user, message = resolve_registration_decision(
        db=db,
        token=token,
        expected_action="approve",
        ip_address=get_client_ip(request),
    )
    return HTMLResponse(
        f"""
        <html>
          <body style="font-family: Arial, sans-serif; padding: 32px; color: #111827;">
            <h1>Approval processed</h1>
            <p><strong>{user.full_name}</strong> ({user.email})</p>
            <p>{message}</p>
          </body>
        </html>
        """
    )


@router.get("/approval/reject", response_class=HTMLResponse)
def reject_registration(
    request: Request,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    user, message = resolve_registration_decision(
        db=db,
        token=token,
        expected_action="reject",
        ip_address=get_client_ip(request),
    )
    return HTMLResponse(
        f"""
        <html>
          <body style="font-family: Arial, sans-serif; padding: 32px; color: #111827;">
            <h1>Rejection processed</h1>
            <p><strong>{user.full_name}</strong> ({user.email})</p>
            <p>{message}</p>
          </body>
        </html>
        """
    )
