"""
Database Connection
"""
import threading
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import get_settings
from app.db.models import Base
from app.services.gate_compliance import get_or_create_gate_policy
from app.services.auth import backfill_user_roles, seed_bootstrap_operator


# The engine is built on first use (or explicitly via configure_database),
# not at import time, so importing the app never touches the filesystem and
# tests can point the whole process at an in-memory database.
_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None
_engine_url: str = ""
_engine_lock = threading.Lock()


def _ensure_sqlite_directory(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return

    sqlite_path = database_url.replace("sqlite:///", "", 1)
    if sqlite_path == ":memory:":
        return

    database_path = Path(sqlite_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)


def _is_memory_sqlite(url: str) -> bool:
    return url in ("sqlite://", "sqlite:///:memory:")


def _build_engine(url: str) -> Engine:
    _ensure_sqlite_directory(url)
    connect_args: dict = {}
    engine_kwargs: dict = {}
    if url.startswith("sqlite"):
        # Sessions are opened from request threads, camera worker threads and
        # the asyncio broadcaster, so SQLite's per-thread check must be off.
        connect_args["check_same_thread"] = False
        if _is_memory_sqlite(url):
            # One shared connection, otherwise every thread gets its own
            # empty in-memory database.
            engine_kwargs["poolclass"] = StaticPool
    engine = create_engine(url, connect_args=connect_args, **engine_kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            # Wait for a writer (the gate thread) instead of failing with
            # "database is locked".
            cursor.execute("PRAGMA busy_timeout=5000")
            # Readers proceed while a writer commits. No-op for :memory:.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


def _configure_locked(url: Optional[str]) -> Engine:
    global _engine, _session_factory, _engine_url
    if _engine is not None:
        _engine.dispose()
    _engine_url = url or get_settings().resolved_database_url
    _engine = _build_engine(_engine_url)
    _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine


def configure_database(url: Optional[str] = None) -> Engine:
    """(Re)build the engine, disposing any existing one.

    Called implicitly on first use with the configured DATABASE_URL; tests call
    it explicitly with ``sqlite:///:memory:`` before creating the app.
    """
    with _engine_lock:
        return _configure_locked(url)


def get_engine() -> Engine:
    with _engine_lock:
        if _engine is None:
            _configure_locked(None)
        return _engine


def get_sessionmaker() -> sessionmaker:
    get_engine()
    return _session_factory


def _current_url() -> str:
    get_engine()
    return _engine_url


class _SessionFactoryProxy:
    """Callable stand-in for the sessionmaker.

    Keeps ``from app.db.connection import SessionLocal`` and ``SessionLocal()``
    working unchanged at every call site while the engine is created lazily.
    """

    def __call__(self, **kwargs) -> Session:
        return get_sessionmaker()(**kwargs)


SessionLocal = _SessionFactoryProxy()


SQLITE_ADDITIVE_MIGRATIONS = {
    "persons": {
        "shift_id": "TEXT",
    },
    "attendance": {
        "ppe_details": "TEXT",
        "camera_source_type": "TEXT",
        "camera_source_id": "TEXT",
        "log_method": "TEXT",
    },
    "users": {
        "password_hash": "TEXT",
        "status": "TEXT DEFAULT 'pending'",
        "approval_token_version": "INTEGER DEFAULT 0",
        "password_reset_token_version": "INTEGER DEFAULT 0",
        "two_factor_secret": "TEXT",
        "two_factor_enabled": "BOOLEAN DEFAULT 0",
        "backup_codes": "TEXT",
        "failed_login_attempts": "INTEGER DEFAULT 0",
        "last_failed_login_at": "DATETIME",
        "lockout_until": "DATETIME",
        "refresh_token": "TEXT",
        "role_department": "TEXT",
        "role": "TEXT",
        "full_name": "TEXT",
        "created_at": "DATETIME",
        "updated_at": "DATETIME",
    },
    "gate_reviews": {
        "review_reasons": "TEXT",
        "ppe_details": "TEXT",
    },
}

SQLITE_INDEX_MIGRATIONS = {
    "users": {
        "idx_users_status": ["status"],
    },
    "audit_logs": {
        "idx_audit_logs_timestamp": ["timestamp"],
        "idx_audit_logs_event_type": ["event_type"],
        "idx_audit_logs_operator_email": ["operator_email"],
    },
}

SQLITE_REDUNDANT_INDEXES = (
    "idx_users_email",
)


def _is_sqlite_engine() -> bool:
    return _current_url().startswith("sqlite")


def _get_table_columns(connection, table_name: str) -> set[str]:
    result = connection.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in result.fetchall()}


def _apply_sqlite_additive_migrations() -> None:
    if not _is_sqlite_engine():
        return

    with get_engine().begin() as connection:
        for table_name, columns in SQLITE_ADDITIVE_MIGRATIONS.items():
            table_exists = connection.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"
                ),
                {"table_name": table_name},
            ).first()
            if not table_exists:
                continue
            existing_columns = _get_table_columns(connection, table_name)
            for column_name, column_ddl in columns.items():
                if column_name in existing_columns:
                    continue
                connection.execute(
                    text(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_ddl}"
                    )
                )


def _apply_sqlite_index_migrations() -> None:
    if not _is_sqlite_engine():
        return

    with get_engine().begin() as connection:
        for table_name, indexes in SQLITE_INDEX_MIGRATIONS.items():
            table_exists = connection.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"
                ),
                {"table_name": table_name},
            ).first()
            if not table_exists:
                continue

            existing_columns = _get_table_columns(connection, table_name)
            for index_name, column_names in indexes.items():
                if any(column_name not in existing_columns for column_name in column_names):
                    continue
                joined_columns = ", ".join(column_names)
                connection.execute(
                    text(
                        f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({joined_columns})"
                    )
                )

        for index_name in SQLITE_REDUNDANT_INDEXES:
            connection.execute(text(f"DROP INDEX IF EXISTS {index_name}"))


def _seed_gate_policy() -> None:
    db = SessionLocal()
    try:
        get_or_create_gate_policy(db)
        backfill_user_roles(db)
        seed_bootstrap_operator(db)
        db.commit()
    finally:
        db.close()


def _backfill_person_shift_ids() -> None:
    """One-time migration: copy shift_id from profile.json into the DB column."""
    try:
        from app.db.models import Person as PersonModel
        from app.services.persons import read_person_profile

        db = SessionLocal()
        try:
            persons = db.query(PersonModel).filter(PersonModel.shift_id.is_(None)).all()
            updated = 0
            for person in persons:
                profile = read_person_profile(person.id)
                disk_shift = profile.get("shift_id")
                if disk_shift in {"day", "swing", "night"}:
                    person.shift_id = disk_shift
                    updated += 1
            if updated:
                db.commit()
        finally:
            db.close()
    except Exception:
        pass  # Non-critical — will be corrected on next write


def init_db():
    """Create all database tables."""
    Base.metadata.create_all(bind=get_engine())
    _apply_sqlite_additive_migrations()
    _apply_sqlite_index_migrations()
    _backfill_person_shift_ids()
    _seed_gate_policy()


def get_db() -> Session:
    """Dependency for getting database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
