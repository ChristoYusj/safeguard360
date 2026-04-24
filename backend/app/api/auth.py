"""
Authentication routes.
"""
from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.orm import Session

from app.config.settings import get_settings
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


def _build_approval_result_html(
    *,
    user: User,
    message: str,
    approved: bool,
) -> str:
    settings = get_settings()
    frontend_url = (settings.FRONTEND_APP_URL or "").strip().rstrip("/")
    sign_in_url = f"{frontend_url}/" if frontend_url else "/"
    title = "Approval processed" if approved else "Rejection processed"
    eyebrow = "Operator Access"
    status_label = "Approved" if approved else "Rejected"
    headline = "Account approved" if approved else "Request rejected"
    helper = (
        "The operator can now return to SafeGuard 360 and sign in."
        if approved
        else "The operator will not be able to sign in with this request."
    )
    tone = "#22c55e" if approved else "#ef4444"
    tone_muted = "rgba(34, 197, 94, 0.14)" if approved else "rgba(239, 68, 68, 0.14)"
    icon_path = (
        '<path d="M20 7L10 17l-5-5" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />'
        if approved
        else '<path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" />'
    )
    safe_name = escape(user.full_name or "Operator")
    safe_email = escape(user.email or "")
    safe_message = escape(message)
    safe_sign_in_url = escape(sign_in_url, quote=True)

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(title)} - SafeGuard 360</title>
    <style>
      :root {{
        color-scheme: dark;
        --bg: #071014;
        --panel: rgba(18, 29, 42, 0.92);
        --panel-strong: rgba(23, 37, 53, 0.96);
        --border: rgba(148, 163, 184, 0.22);
        --text: #f8fafc;
        --muted: #9ca3af;
        --soft: #cbd5e1;
        --accent: #22d3ee;
        --tone: {tone};
        --tone-muted: {tone_muted};
      }}
      * {{
        box-sizing: border-box;
      }}
      body {{
        min-height: 100vh;
        margin: 0;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: var(--text);
        background:
          linear-gradient(rgba(148, 163, 184, 0.045) 1px, transparent 1px),
          linear-gradient(90deg, rgba(148, 163, 184, 0.045) 1px, transparent 1px),
          linear-gradient(135deg, #071014 0%, #0b1620 48%, #101827 100%);
        background-size: 44px 44px, 44px 44px, auto;
      }}
      main {{
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 32px 18px;
      }}
      .card {{
        width: min(560px, 100%);
        border: 1px solid var(--border);
        border-radius: 24px;
        background: linear-gradient(180deg, var(--panel-strong), var(--panel));
        box-shadow: 0 24px 80px rgba(0, 0, 0, 0.38);
        overflow: hidden;
      }}
      .topbar {{
        height: 5px;
        background: linear-gradient(90deg, var(--accent), var(--tone));
      }}
      .content {{
        padding: 30px;
      }}
      .brand {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        margin-bottom: 28px;
      }}
      .brand-name {{
        margin: 0;
        color: var(--muted);
        font-size: 12px;
        font-weight: 800;
        letter-spacing: 0.14em;
        text-transform: uppercase;
      }}
      .badge {{
        display: inline-flex;
        align-items: center;
        min-height: 32px;
        border: 1px solid color-mix(in srgb, var(--tone) 42%, transparent);
        border-radius: 999px;
        padding: 0 12px;
        color: var(--tone);
        background: var(--tone-muted);
        font-size: 12px;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }}
      .status-icon {{
        display: grid;
        place-items: center;
        width: 58px;
        height: 58px;
        margin-bottom: 18px;
        border: 1px solid color-mix(in srgb, var(--tone) 46%, transparent);
        border-radius: 18px;
        color: var(--tone);
        background: var(--tone-muted);
      }}
      h1 {{
        margin: 0;
        font-size: clamp(30px, 6vw, 44px);
        line-height: 1.05;
        letter-spacing: 0;
      }}
      .message {{
        margin: 14px 0 0;
        color: var(--soft);
        font-size: 16px;
        line-height: 1.65;
      }}
      .identity {{
        margin: 26px 0;
        padding: 16px;
        border: 1px solid var(--border);
        border-radius: 16px;
        background: rgba(15, 23, 42, 0.62);
      }}
      .identity-label {{
        margin: 0 0 6px;
        color: var(--muted);
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }}
      .identity-name {{
        margin: 0;
        font-size: 16px;
        font-weight: 800;
      }}
      .identity-email {{
        margin: 4px 0 0;
        color: var(--muted);
        font-size: 14px;
        overflow-wrap: anywhere;
      }}
      .actions {{
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 12px;
      }}
      .button {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 46px;
        border-radius: 14px;
        padding: 0 18px;
        color: #041015;
        background: linear-gradient(135deg, var(--accent), var(--tone));
        font-size: 14px;
        font-weight: 800;
        text-decoration: none;
      }}
      .hint {{
        margin: 0;
        color: var(--muted);
        font-size: 13px;
      }}
      @media (max-width: 520px) {{
        .content {{
          padding: 24px;
        }}
        .brand {{
          align-items: flex-start;
          flex-direction: column;
        }}
      }}
    </style>
  </head>
  <body>
    <main>
      <section class="card" aria-labelledby="approval-title">
        <div class="topbar"></div>
        <div class="content">
          <div class="brand">
            <p class="brand-name">SafeGuard 360</p>
            <span class="badge">{escape(status_label)}</span>
          </div>
          <div class="status-icon" aria-hidden="true">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
              {icon_path}
            </svg>
          </div>
          <p class="brand-name">{escape(eyebrow)}</p>
          <h1 id="approval-title">{escape(headline)}</h1>
          <p class="message">{safe_message}</p>
          <div class="identity">
            <p class="identity-label">Operator Request</p>
            <p class="identity-name">{safe_name}</p>
            <p class="identity-email">{safe_email}</p>
          </div>
          <div class="actions">
            <a class="button" href="{safe_sign_in_url}">Go to sign in</a>
            <p class="hint">{escape(helper)}</p>
          </div>
        </div>
      </section>
    </main>
  </body>
</html>"""


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
        _build_approval_result_html(
            user=user,
            message=message,
            approved=True,
        )
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
        _build_approval_result_html(
            user=user,
            message=message,
            approved=False,
        )
    )
