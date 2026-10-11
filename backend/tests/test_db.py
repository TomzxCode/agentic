"""Database migrations and the post-init column patcher.

Each test points `agentic.db.engine` at a throwaway SQLite file with a legacy
schema, so the migrations can be exercised without touching the real database.
"""

import pytest
import sqlalchemy
from sqlmodel import create_engine

from agentic import db

# Engines built per test must be disposed so their pooled SQLite connections
# are closed rather than collected (which emits ResourceWarning).
_engines: list = []


def _engine(tmp_path, name: str):
    engine = create_engine(f"sqlite:///{tmp_path / name}")
    _engines.append(engine)
    return engine


@pytest.fixture(autouse=True)
def _dispose_engines():
    yield
    while _engines:
        _engines.pop().dispose()


def test_migrate_problem_to_task_renames_table_and_columns(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "a.db")
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("CREATE TABLE problem (id VARCHAR PRIMARY KEY, title VARCHAR)"))
        conn.execute(sqlalchemy.text("CREATE TABLE association (id VARCHAR PRIMARY KEY, problem_id VARCHAR)"))
        conn.execute(sqlalchemy.text("CREATE TABLE timelineevent (id VARCHAR PRIMARY KEY, message VARCHAR)"))
        conn.execute(sqlalchemy.text("INSERT INTO timelineevent (id, message) VALUES ('1', 'Problem created')"))
    monkeypatch.setattr(db, "engine", engine)

    db._migrate_problem_to_task()

    tables = set(sqlalchemy.inspect(engine).get_table_names())
    assert "task" in tables and "problem" not in tables
    columns = {column["name"] for column in sqlalchemy.inspect(engine).get_columns("association")}
    assert "task_id" in columns and "problem_id" not in columns
    with engine.connect() as conn:
        assert conn.execute(sqlalchemy.text("SELECT message FROM timelineevent")).scalar() == "Task created"


def test_migrate_problem_to_task_leaves_already_migrated_columns(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "b.db")
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("CREATE TABLE task (id VARCHAR PRIMARY KEY)"))
        conn.execute(
            sqlalchemy.text("CREATE TABLE worktree (id VARCHAR PRIMARY KEY, task_id VARCHAR, problem_id VARCHAR)")
        )
    monkeypatch.setattr(db, "engine", engine)

    db._migrate_problem_to_task()

    columns = {column["name"] for column in sqlalchemy.inspect(engine).get_columns("worktree")}
    # The stale column is left in place when the new one already exists.
    assert "task_id" in columns and "problem_id" in columns


def test_migrate_problem_to_task_without_tables_is_a_noop(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "c.db")
    monkeypatch.setattr(db, "engine", engine)
    db._migrate_problem_to_task()


def test_migrate_task_repositories_moves_the_single_value(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "d.db")
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("CREATE TABLE task (id VARCHAR PRIMARY KEY, repository_id VARCHAR)"))
        conn.execute(
            sqlalchemy.text(
                "CREATE TABLE taskrepository "
                "(id VARCHAR PRIMARY KEY, task_id VARCHAR, repository_id VARCHAR, created_at TIMESTAMP)"
            )
        )
        conn.execute(sqlalchemy.text("INSERT INTO task (id, repository_id) VALUES ('t1', 'r1')"))
    monkeypatch.setattr(db, "engine", engine)

    db._migrate_task_repositories()

    with engine.connect() as conn:
        moved = conn.execute(sqlalchemy.text("SELECT repository_id FROM taskrepository WHERE task_id='t1'")).scalar()
        cleared = conn.execute(sqlalchemy.text("SELECT repository_id FROM task WHERE id='t1'")).scalar()
    assert moved == "r1" and cleared is None


def test_migrate_task_repositories_is_a_noop_without_the_column(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "e.db")
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("CREATE TABLE task (id VARCHAR PRIMARY KEY)"))
        conn.execute(sqlalchemy.text("CREATE TABLE taskrepository (id VARCHAR PRIMARY KEY)"))
    monkeypatch.setattr(db, "engine", engine)
    db._migrate_task_repositories()


def test_migrate_task_repositories_is_a_noop_without_tables(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "f.db")
    monkeypatch.setattr(db, "engine", engine)
    db._migrate_task_repositories()


def test_ensure_columns_adds_missing_post_init_columns(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "g.db")
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("CREATE TABLE harness (id VARCHAR PRIMARY KEY, name VARCHAR)"))
        conn.execute(sqlalchemy.text("CREATE TABLE task (id VARCHAR PRIMARY KEY, title VARCHAR)"))
    monkeypatch.setattr(db, "engine", engine)

    db._ensure_columns()

    harness_columns = {column["name"] for column in sqlalchemy.inspect(engine).get_columns("harness")}
    task_columns = {column["name"] for column in sqlalchemy.inspect(engine).get_columns("task")}
    assert "resume_command" in harness_columns
    assert "group_id" in task_columns

    # A second pass is a no-op now that the columns exist.
    db._ensure_columns()


def test_ensure_columns_without_tables_is_a_noop(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "h.db")
    monkeypatch.setattr(db, "engine", engine)
    db._ensure_columns()
