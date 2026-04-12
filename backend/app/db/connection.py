"""
Database Connection
"""
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings
from app.db.models import Base
from app.services.gate_compliance import get_or_create_gate_policy
from app.services.auth import seed_bootstrap_operator


# Create engine
settings = get_settings()

def _ensure_sqlite_directory(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return

    sqlite_path = database_url.replace("sqlite:///", "", 1)
    if sqlite_path == ":memory:":
        return

    database_path = Path(sqlite_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)


resolved_database_url = settings.resolved_database_url
_ensure_sqlite_directory(resolved_database_url)

engine = create_engine(
    resolved_database_url,
    connect_args={"check_same_thread": False}  # SQLite specific
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


SQLITE_ADDITIVE_MIGRATIONS = {
    "attendance": {
        "ppe_details": "TEXT",
        "camera_source_type": "TEXT",
        "camera_source_id": "TEXT",
        "log_method": "TEXT",
    },
    "users": {
        "password_hash": "TEXT",
        "status": "TEXT DEFAULT 'pending'",
        "two_factor_secret": "TEXT",
        "two_factor_enabled": "BOOLEAN DEFAULT 0",
        "backup_codes": "TEXT",
        "failed_login_attempts": "INTEGER DEFAULT 0",
        "last_failed_login_at": "DATETIME",
        "lockout_until": "DATETIME",
        "refresh_token": "TEXT",
        "role_department": "TEXT",
        "full_name": "TEXT",
        "created_at": "DATETIME",
        "updated_at": "DATETIME",
    },
    "gate_reviews": {
        "review_reasons": "TEXT",
        "ppe_details": "TEXT",
    },
}


def _is_sqlite_engine() -> bool:
    return str(resolved_database_url).startswith("sqlite")


def _get_table_columns(connection, table_name: str) -> set[str]:
    result = connection.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in result.fetchall()}


def _apply_sqlite_additive_migrations() -> None:
    if not _is_sqlite_engine():
        return

    with engine.begin() as connection:
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


def _seed_gate_policy() -> None:
    db = SessionLocal()
    try:
        get_or_create_gate_policy(db)
        seed_bootstrap_operator(db)
        db.commit()
    finally:
        db.close()


def init_db():
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)
    _apply_sqlite_additive_migrations()
    _seed_gate_policy()


def get_db() -> Session:
    """Dependency for getting database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
