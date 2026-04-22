"""
Shared test fixtures. Uses an in-memory SQLite engine so tests don't touch
the real data directory and don't require any env/.env config.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make sure the `app` package is importable when tests are run from /backend.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Provide dummy secrets so settings validation doesn't blow up on import.
os.environ.setdefault("JWT_ACCESS_SECRET", "test-access")
os.environ.setdefault("JWT_REFRESH_SECRET", "test-refresh")
os.environ.setdefault("JWT_APPROVAL_SECRET", "test-approval")
os.environ.setdefault("TOTP_ENCRYPTION_KEY", "0" * 44)
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base


@pytest.fixture()
def db_session():
    """Fresh in-memory DB per test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
