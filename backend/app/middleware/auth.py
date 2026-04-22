"""
Authentication middleware for protected operator routes.
"""
from __future__ import annotations

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.db.connection import SessionLocal
from app.services.auth import ACCESS_COOKIE_NAME, get_user_by_access_token
from app.services.rbac import has_api_role_access


class OperatorAuthMiddleware(BaseHTTPMiddleware):
    """Require operator authentication for protected API routes."""

    PUBLIC_PATH_PREFIXES = (
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/password-reset/request",
        "/api/auth/password-reset/confirm",
        "/api/auth/refresh",
        "/api/auth/logout",
        "/api/auth/2fa/verify",
        "/api/auth/approval/",
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
            if not has_api_role_access(user.role, path, request.method):
                return JSONResponse({"detail": "Forbidden."}, status_code=status.HTTP_403_FORBIDDEN)
            request.state.user = user
            request.state.auth_claims = claims
        except Exception as exc:
            detail = getattr(exc, "detail", "Authentication required.")
            status_code = getattr(exc, "status_code", status.HTTP_401_UNAUTHORIZED)
            return JSONResponse({"detail": detail}, status_code=status_code)
        finally:
            db.close()

        return await call_next(request)
