from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.config.settings import get_settings
from app.db.connection import SessionLocal
from app.db.models import User
from app.services.auth import hash_password, normalize_email


def main() -> int:
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
        db.add(admin_user)
        db.commit()

        print(f"Bootstrap admin password reset for {admin_email}.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
