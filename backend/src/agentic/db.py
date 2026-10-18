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


_initialized = False


def create_db_and_tables() -> None:
    global _initialized
    if _initialized:
        return
    # Import every model module so its tables are registered on SQLModel.metadata
    # before create_all.
    from .models import (  # noqa: F401
        agents,
        base,
        changes,
        items,
        repositories,
        schedules,
        system,
        tasks,
    )

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.worktree_root.mkdir(parents=True, exist_ok=True)
    _migrate_problem_to_task()
    SQLModel.metadata.create_all(engine)
    _migrate_task_repositories()
    _migrate_person_aliases()
    _ensure_columns()
    _initialized = True


def _migrate_task_repositories() -> None:
    """Move the old single task.repository_id into the task_repository table.

    The column is left in place (SQLite cannot drop a column that carries a
    foreign key) but is emptied, so it no longer references anything.
    """
    tables = set(inspect(engine).get_table_names())
    if "task" not in tables or "taskrepository" not in tables:
        return
    columns = {column["name"] for column in inspect(engine).get_columns("task")}
    if "repository_id" not in columns:
        return
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT OR IGNORE INTO taskrepository (id, task_id, repository_id, created_at) "
                "SELECT lower(hex(randomblob(6))), id, repository_id, CURRENT_TIMESTAMP "
                "FROM task WHERE repository_id IS NOT NULL"
            )
        )
        connection.execute(text("UPDATE task SET repository_id = NULL"))


def _migrate_person_aliases() -> None:
    """Move a person's old single handle and email into the personalias table.

    The columns are left in place (SQLite column drops are disruptive) but are
    emptied, so they no longer carry identity. A fresh database never has them.
    """
    tables = set(inspect(engine).get_table_names())
    if "person" not in tables or "personalias" not in tables:
        return
    columns = {column["name"] for column in inspect(engine).get_columns("person")}
    legacy = [column for column in ("handle", "email") if column in columns]
    if not legacy:
        return
    with engine.begin() as connection:
        for column in legacy:
            connection.execute(
                text(
                    f"INSERT OR IGNORE INTO personalias (id, person_id, value, created_at) "
                    f"SELECT lower(hex(randomblob(6))), id, {column}, CURRENT_TIMESTAMP "
                    f"FROM person WHERE {column} IS NOT NULL AND trim({column}) <> ''"
                )
            )
            connection.execute(text(f"UPDATE person SET {column} = NULL"))


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
        if "default_model_source" not in harness_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE harness ADD COLUMN default_model_source VARCHAR"))
    if "agentrun" in inspector.get_table_names():
        run_columns = {column["name"] for column in inspector.get_columns("agentrun")}
        if "model" not in run_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE agentrun ADD COLUMN model VARCHAR"))
    if "task" in inspector.get_table_names():
        task_columns = {column["name"] for column in inspector.get_columns("task")}
        if "group_id" not in task_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE task ADD COLUMN group_id VARCHAR"))
        if "deadline" not in task_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE task ADD COLUMN deadline DATETIME"))
    if "timelineevent" in inspector.get_table_names():
        timeline_columns = {column["name"] for column in inspector.get_columns("timelineevent")}
        with engine.begin() as connection:
            # The DEFAULT backfills pre-existing rows, so they read as api/human.
            if "client" not in timeline_columns:
                connection.execute(text("ALTER TABLE timelineevent ADD COLUMN client VARCHAR NOT NULL DEFAULT 'api'"))
            if "actor" not in timeline_columns:
                connection.execute(text("ALTER TABLE timelineevent ADD COLUMN actor VARCHAR NOT NULL DEFAULT 'human'"))
    if "sourceitem" in inspector.get_table_names():
        item_columns = {column["name"] for column in inspector.get_columns("sourceitem")}
        if "title_custom" not in item_columns:
            with engine.begin() as connection:
                # Pre-existing items read as auto-titled; DEFAULT backfills them.
                connection.execute(text("ALTER TABLE sourceitem ADD COLUMN title_custom BOOLEAN NOT NULL DEFAULT 0"))
    if "scheduledtask" in inspector.get_table_names():
        schedule_columns = {column["name"] for column in inspector.get_columns("scheduledtask")}
        if "timezone" not in schedule_columns:
            with engine.begin() as connection:
                # NULL means the task follows the server's timezone.
                connection.execute(text("ALTER TABLE scheduledtask ADD COLUMN timezone VARCHAR"))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
