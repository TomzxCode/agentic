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
    _migrate_problem_to_task()
    SQLModel.metadata.create_all(engine)
    _ensure_columns()


def _migrate_problem_to_task() -> None:
    """Rename the 'problem' table/columns to 'task' on an existing database."""
    tables = set(inspect(engine).get_table_names())
    with engine.begin() as connection:
        if "problem" in tables and "task" not in tables:
            connection.execute(text("ALTER TABLE problem RENAME TO task"))
            tables.discard("problem")
            tables.add("task")
        for table in ("association", "worktree", "agentrun", "timelineevent"):
            if table not in tables:
                continue
            columns = {column["name"] for column in inspect(engine).get_columns(table)}
            if "problem_id" in columns and "task_id" not in columns:
                connection.execute(text(f"ALTER TABLE {table} RENAME COLUMN problem_id TO task_id"))
        if "timelineevent" in tables:
            connection.execute(
                text(
                    "UPDATE timelineevent SET message = replace(message, 'Problem ', 'Task ') "
                    "WHERE message LIKE '%Problem %'"
                )
            )


def _ensure_columns() -> None:
    """Add columns introduced after the initial schema (SQLModel builds, not migrates)."""
    inspector = inspect(engine)
    if "harness" in inspector.get_table_names():
        harness_columns = {column["name"] for column in inspector.get_columns("harness")}
        if "resume_command" not in harness_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE harness ADD COLUMN resume_command VARCHAR"))
    if "task" in inspector.get_table_names():
        task_columns = {column["name"] for column in inspector.get_columns("task")}
        if "group_id" not in task_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE task ADD COLUMN group_id VARCHAR"))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
