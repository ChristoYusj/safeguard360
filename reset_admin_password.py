"""Recover the bootstrap admin account from the repo-root .env.

Resets the password to BOOTSTRAP_ADMIN_PASSWORD and, because this is the
break-glass path, also revokes the refresh session, invalidates outstanding
reset links, clears any lockout and reactivates the account. Pass
--disable-2fa when the authenticator device is lost as well. Every run is
written to the audit log.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.config.settings import get_settings  # noqa: E402
from app.db.connection import SessionLocal  # noqa: E402
from app.db.models import User  # noqa: E402
from app.services.audit import AUDIT_PASSWORD_CHANGE, record_audit_event  # noqa: E402
from app.services.auth import hash_password, normalize_email  # noqa: E402
from app.services.rbac import USER_STATUS_ACTIVE  # noqa: E402


def reset_admin(*, disable_two_factor: bool = False) -> int:
    settings = get_settings()
    admin_email = normalize_email(settings.ADMIN_EMAIL)
    bootstrap_password = settings.BOOTSTRAP_ADMIN_PASSWORD or ""

    if not admin_email:
        print("ADMIN_EMAIL is not set in the repo-root .env file.")
        return 1

    if not bootstrap_password:
        print("BOOTSTRAP_ADMIN_PASSWORD is not set in the repo-root .env file.")
        return 1

    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.email == admin_email).first()
        if not admin_user:
            print(f"Bootstrap admin account not found for {admin_email}.")
            return 1

        admin_user.password_hash = hash_password(bootstrap_password)
        # Anyone holding the old refresh cookie must not keep minting access
        # tokens after a break-glass reset; pending reset links die with it.
        admin_user.refresh_token = None
        admin_user.password_reset_token_version = (admin_user.password_reset_token_version or 0) + 1
        admin_user.failed_login_attempts = 0
        admin_user.last_failed_login_at = None
        admin_user.lockout_until = None
        admin_user.status = USER_STATUS_ACTIVE
        actions = ["password reset", "refresh session revoked", "lockout cleared"]
        if disable_two_factor:
            admin_user.two_factor_enabled = False
            admin_user.two_factor_secret = None
            admin_user.backup_codes = None
            actions.append("two-factor disabled")

        db.add(admin_user)
        record_audit_event(
            db,
            operator_email=admin_email,
            event_type=AUDIT_PASSWORD_CHANGE,
            ip_address="cli",
            detail="reset_admin_password.py: " + ", ".join(actions) + ".",
        )
        db.commit()

        print(f"Bootstrap admin recovered for {admin_email}: {', '.join(actions)}.")
        return 0
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--disable-2fa",
        action="store_true",
        help="also turn off two-factor authentication and discard backup codes",
    )
    args = parser.parse_args(argv)
    return reset_admin(disable_two_factor=args.disable_2fa)


if __name__ == "__main__":
    raise SystemExit(main())
