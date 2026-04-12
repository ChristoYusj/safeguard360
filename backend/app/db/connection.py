"""
Database Connection
"""
import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings
from app.db.models import Base
from app.services.gate_compliance import get_or_create_gate_policy


# Create engine
settings = get_settings()

# Ensure data directory exists
os.makedirs("data", exist_ok=True)

engine = create_engine(
    settings.DATABASE_URL,
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
    "gate_reviews": {
        "review_reasons": "TEXT",
        "ppe_details": "TEXT",
    },
}


def _is_sqlite_engine() -> bool:
    return str(settings.DATABASE_URL).startswith("sqlite")


def _get_table_columns(connection, table_name: str) -> set[str]:
    result = connection.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in result.fetchall()}


def _apply_sqlite_additive_migrations() -> None:
    if not _is_sqlite_engine():
        return

    with engine.begin() as connection:
        for table_name, columns in SQLITE_ADDITIVE_MIGRATIONS.items():
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
