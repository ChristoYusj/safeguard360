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
# Hard-set, not setdefault: a DATABASE_URL exported in the developer's shell
# must never make the suite touch a real database.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
# create_app() refuses to start without these; the bootstrap admin they seed is
# what the HTTP fixtures log in as.
os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "Bootstrap-Passw0rd!2026")
os.environ.setdefault("FRONTEND_APP_URL", "http://testserver")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base

TEST_ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
TEST_ADMIN_PASSWORD = os.environ["BOOTSTRAP_ADMIN_PASSWORD"]


@pytest.fixture()
def client():
    """A TestClient over the real app on a fresh in-memory database.

    configure_database swaps the process-wide engine for a StaticPool
    in-memory one, so the middleware, gate service and websocket code (which
    call SessionLocal() directly) all see the same tables the test does.
    Entering the client runs the lifespan: init_db seeds the gate policy and the
    bootstrap admin from the environment above.
    """
    from fastapi.testclient import TestClient

    from app.db import connection
    from app.factory import create_app
    from app.services import auth as auth_service

    connection.configure_database("sqlite:///:memory:")
    # The IP failure table is process-global; every TestClient request comes
    # from the same address, so lockout tests would poison later logins.
    auth_service._IP_FAILURES.clear()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    # Leave a fresh, empty engine behind so state never leaks into the next test.
    connection.configure_database("sqlite:///:memory:")


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
