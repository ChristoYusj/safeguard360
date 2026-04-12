"""
Authentication middleware for protected operator routes.
"""
from __future__ import annotations

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.db.connection import SessionLocal
from app.services.auth import ACCESS_COOKIE_NAME, get_user_by_access_token


class OperatorAuthMiddleware(BaseHTTPMiddleware):
    """Require operator authentication for protected API routes."""

    PUBLIC_PATH_PREFIXES = (
        "/api/auth/login",
        "/api/auth/logout",
        "/docs",
        "/redoc",
        "/openapi.json",
    )

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if not path.startswith("/api/") or path.startswith(self.PUBLIC_PATH_PREFIXES):
            return await call_next(request)

        db = SessionLocal()
        try:
            token = request.cookies.get(ACCESS_COOKIE_NAME)
            user, claims = get_user_by_access_token(db, token)
            request.state.user = user
            request.state.auth_claims = claims
        except Exception as exc:
            detail = getattr(exc, "detail", "Authentication required.")
            status_code = getattr(exc, "status_code", status.HTTP_401_UNAUTHORIZED)
            return JSONResponse({"detail": detail}, status_code=status_code)
        finally:
            db.close()

        return await call_next(request)
