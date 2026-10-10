"""Database engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import event, inspect, text
from sqlmodel import Session, SQLModel, create_engine

from .config import settings

engine = create_engine(
    settings.sqlalchemy_url,
    echo=False,
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_db_and_tables() -> None:
    # Import models so they are registered on SQLModel.metadata before create_all.
    from . import models  # noqa: F401

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.worktree_root.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)
    _ensure_columns()


def _ensure_columns() -> None:
    """Add columns introduced after the initial schema (SQLModel builds, not migrates)."""
    inspector = inspect(engine)
    if "harness" in inspector.get_table_names():
        harness_columns = {column["name"] for column in inspector.get_columns("harness")}
        if "resume_command" not in harness_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE harness ADD COLUMN resume_command VARCHAR"))
    if "problem" in inspector.get_table_names():
        problem_columns = {column["name"] for column in inspector.get_columns("problem")}
        if "group_id" not in problem_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE problem ADD COLUMN group_id VARCHAR"))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
