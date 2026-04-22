"""
Admin-only user management routes.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.db.models import User
from app.services.auth import serialize_user
from app.services.audit import (
    AUDIT_ACCOUNT_APPROVED,
    AUDIT_ACCOUNT_DEACTIVATED,
    AUDIT_ACCOUNT_DELETED,
    AUDIT_ACCOUNT_REACTIVATED,
    AUDIT_ACCOUNT_REJECTED,
    AUDIT_ROLE_CHANGED,
    record_audit_event,
)
from app.services.rbac import (
    ADMIN_ROLE,
    ALL_USER_ROLES,
    ALL_USER_STATUSES,
    USER_STATUS_ACTIVE,
    USER_STATUS_PENDING,
    USER_STATUS_REJECTED,
    USER_STATUS_RESTRICTED,
    get_role_label,
    normalize_user_role,
    normalize_user_status,
)


router = APIRouter()


class AdminUserUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    role: str | None = None
    status: str | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_user_role(value)
        if normalized not in ALL_USER_ROLES:
            allowed = ", ".join(sorted(ALL_USER_ROLES))
            raise ValueError(f"Role must be one of: {allowed}.")
        return normalized

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_user_status(value)
        if normalized not in ALL_USER_STATUSES:
            allowed = ", ".join(sorted(ALL_USER_STATUSES))
            raise ValueError(f"Status must be one of: {allowed}.")
        return normalized


def _serialize_admin_user(user: User) -> dict:
    payload = serialize_user(user)
    payload["created_at"] = user.created_at.isoformat() if user.created_at else None
    payload["updated_at"] = user.updated_at.isoformat() if user.updated_at else None
    payload["failed_login_attempts"] = int(user.failed_login_attempts or 0)
    payload["last_failed_login_at"] = (
        user.last_failed_login_at.isoformat() if user.last_failed_login_at else None
    )
    payload["lockout_until"] = user.lockout_until.isoformat() if user.lockout_until else None
    payload["is_locked"] = bool(user.lockout_until and user.lockout_until > datetime.utcnow())
    return payload


def _get_admin_user(request: Request, db: Session) -> User:
    current_user = getattr(request.state, "user", None)
    if not isinstance(current_user, User):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    admin_user = db.query(User).filter(User.id == current_user.id).first()
    if not admin_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    if admin_user.role != ADMIN_ROLE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    return admin_user


@router.get("/users")
def list_users(request: Request, db: Session = Depends(get_db)):
    _get_admin_user(request, db)
    users = db.query(User).order_by(User.created_at.asc(), User.email.asc()).all()
    return {
        "users": [_serialize_admin_user(user) for user in users],
    }


@router.patch("/users/{user_id}")
def update_user_account(
    user_id: str,
    payload: AdminUserUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    admin_user = _get_admin_user(request, db)
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if payload.role is None and payload.status is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No updates were provided.")

    if payload.status == "pending":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Pending status can only be created through registration.",
        )

    if target_user.id == admin_user.id:
        if payload.role and payload.role != ADMIN_ROLE:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot remove your own admin role.")
        if payload.status and payload.status != USER_STATUS_ACTIVE:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot deactivate your own admin account.")

    if payload.role is not None:
        previous_role = target_user.role
        target_user.role = payload.role
        target_user.role_department = get_role_label(payload.role)
        if previous_role != payload.role:
            record_audit_event(
                db,
                operator_email=target_user.email,
                event_type=AUDIT_ROLE_CHANGED,
                ip_address=request.client.host if request.client else None,
                detail=(
                    f"Role changed from {previous_role or 'unknown'} to {payload.role} "
                    f"by {admin_user.email}."
                ),
            )

    if payload.status is not None:
        previous_status = target_user.status
        target_user.status = payload.status
        event_type = None
        detail = None
        if previous_status == USER_STATUS_PENDING and payload.status == USER_STATUS_ACTIVE:
            event_type = AUDIT_ACCOUNT_APPROVED
            detail = f"Account approved by {admin_user.email} from the admin console."
        elif previous_status == USER_STATUS_PENDING and payload.status == USER_STATUS_REJECTED:
            event_type = AUDIT_ACCOUNT_REJECTED
            detail = f"Account rejected by {admin_user.email} from the admin console."
        elif previous_status == USER_STATUS_ACTIVE and payload.status == USER_STATUS_RESTRICTED:
            event_type = AUDIT_ACCOUNT_DEACTIVATED
            detail = f"Account deactivated by {admin_user.email}."
        elif previous_status == USER_STATUS_RESTRICTED and payload.status == USER_STATUS_ACTIVE:
            event_type = AUDIT_ACCOUNT_REACTIVATED
            detail = f"Account reactivated by {admin_user.email}."
        if event_type:
            record_audit_event(
                db,
                operator_email=target_user.email,
                event_type=event_type,
                ip_address=request.client.host if request.client else None,
                detail=detail,
            )

    target_user.updated_at = datetime.utcnow()
    db.add(target_user)
    db.commit()
    db.refresh(target_user)
    return {"user": _serialize_admin_user(target_user)}


@router.delete("/users/{user_id}")
def delete_user_account(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    admin_user = _get_admin_user(request, db)
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if target_user.id == admin_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot delete your own admin account.")

    record_audit_event(
        db,
        operator_email=target_user.email,
        event_type=AUDIT_ACCOUNT_DELETED,
        ip_address=request.client.host if request.client else None,
        detail=f"Account deleted by {admin_user.email}.",
    )
    db.delete(target_user)
    db.commit()
    return {"success": True}


@router.post("/users/{user_id}/unlock")
def unlock_user_account(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    admin_user = _get_admin_user(request, db)
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    target_user.failed_login_attempts = 0
    target_user.last_failed_login_at = None
    target_user.lockout_until = None
    target_user.updated_at = datetime.utcnow()

    db.add(target_user)
    db.commit()
    db.refresh(target_user)
    return {
        "message": f"Account lockout cleared by {admin_user.email}.",
        "user": _serialize_admin_user(target_user),
    }
