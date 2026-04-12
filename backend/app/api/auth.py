"""
Authentication routes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.db.models import User
from app.services.auth import (
    authenticate_operator,
    clear_auth_cookies,
    clear_refresh_token,
    issue_login_tokens,
    serialize_user,
    set_auth_cookies,
)


router = APIRouter()


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str
    password: str


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = authenticate_operator(
        db=db,
        request=request,
        email=payload.email,
        password=payload.password,
    )
    access_token, refresh_token = issue_login_tokens(db, user)
    response = JSONResponse({"user": serialize_user(user)})
    set_auth_cookies(response, access_token, refresh_token)
    return response


@router.get("/me")
def get_current_operator(request: Request):
    current_user = getattr(request.state, "user", None)
    if not current_user:
        return JSONResponse({"detail": "Authentication required."}, status_code=401)
    return {"user": serialize_user(current_user)}


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    current_user = getattr(request.state, "user", None)
    if isinstance(current_user, User):
        persistent_user = db.query(User).filter(User.id == current_user.id).first()
        if persistent_user:
            clear_refresh_token(persistent_user)
            db.add(persistent_user)
            db.commit()

    response = JSONResponse({"success": True})
    clear_auth_cookies(response)
    return response
