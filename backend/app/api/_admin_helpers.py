"""
Shared helpers for admin-only API routes.
"""
from __future__ import annotations

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.models import User
from app.services.rbac import ADMIN_ROLE


def get_admin_user(request: Request, db: Session) -> User:
    current_user = getattr(request.state, "user", None)
    if not isinstance(current_user, User):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    admin_user = db.query(User).filter(User.id == current_user.id).first()
    if not admin_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    if admin_user.role != ADMIN_ROLE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    return admin_user
