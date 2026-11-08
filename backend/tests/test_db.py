"""Database migrations and the post-init column patcher.

Each test points `agentic.db.engine` at a throwaway SQLite file with a legacy
schema, so the migrations can be exercised without touching the real database.
"""

import json

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


def test_migrate_next_steps_to_checklist_moves_and_deduplicates(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "p.db")
    steps = [
        {"text": "Existing", "done": False},
        {"text": "One", "done": False},
        {"text": "Two", "done": True},
        {"text": "one", "done": True},
    ]
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("CREATE TABLE task (id VARCHAR PRIMARY KEY, next_steps VARCHAR)"))
        conn.execute(
            sqlalchemy.text(
                "CREATE TABLE checklistitem "
                "(id VARCHAR PRIMARY KEY, task_id VARCHAR, template_id VARCHAR, text VARCHAR, position INTEGER, "
                "done BOOLEAN, done_at DATETIME, converted_task_id VARCHAR, created_at DATETIME, updated_at DATETIME)"
            )
        )
        conn.execute(
            sqlalchemy.text("INSERT INTO task (id, next_steps) VALUES ('t1', :steps)"),
            {"steps": json.dumps(steps)},
        )
        conn.execute(
            sqlalchemy.text(
                "INSERT INTO checklistitem (id, task_id, text, position, done) VALUES ('i1', 't1', 'Existing', 0, 0)"
            )
        )
    monkeypatch.setattr(db, "engine", engine)

    db._migrate_next_steps_to_checklist()

    with engine.connect() as conn:
        rows = conn.execute(
            sqlalchemy.text("SELECT text, position, done FROM checklistitem WHERE task_id='t1' ORDER BY position")
        ).all()
        cleared = conn.execute(sqlalchemy.text("SELECT next_steps FROM task WHERE id='t1'")).scalar()
    # The existing item is kept once, the duplicate collapses, and the new
    # items append after it carrying their done state.
    assert [tuple(row) for row in rows] == [("Existing", 0, 0), ("One", 1, 0), ("Two", 2, 1)]
    assert cleared == "[]"

    # A second pass adds nothing now that the field is empty.
    db._migrate_next_steps_to_checklist()
    with engine.connect() as conn:
        assert conn.execute(sqlalchemy.text("SELECT count(*) FROM checklistitem")).scalar() == 3


def test_migrate_next_steps_to_checklist_without_the_column_is_a_noop(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "q.db")
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("CREATE TABLE task (id VARCHAR PRIMARY KEY)"))
        conn.execute(sqlalchemy.text("CREATE TABLE checklistitem (id VARCHAR PRIMARY KEY)"))
    monkeypatch.setattr(db, "engine", engine)
    db._migrate_next_steps_to_checklist()


def test_ensure_columns_adds_missing_post_init_columns(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "g.db")
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("CREATE TABLE harness (id VARCHAR PRIMARY KEY, name VARCHAR)"))
        conn.execute(sqlalchemy.text("CREATE TABLE task (id VARCHAR PRIMARY KEY, title VARCHAR)"))
        conn.execute(sqlalchemy.text("CREATE TABLE timelineevent (id VARCHAR PRIMARY KEY, type VARCHAR)"))
        conn.execute(sqlalchemy.text("INSERT INTO timelineevent (id, type) VALUES ('e1', 'created')"))
        conn.execute(sqlalchemy.text("CREATE TABLE sourceitem (id VARCHAR PRIMARY KEY, title VARCHAR)"))
        conn.execute(sqlalchemy.text("INSERT INTO sourceitem (id, title) VALUES ('i1', 'A title')"))
    monkeypatch.setattr(db, "engine", engine)

    db._ensure_columns()

    harness_columns = {column["name"] for column in sqlalchemy.inspect(engine).get_columns("harness")}
    task_columns = {column["name"] for column in sqlalchemy.inspect(engine).get_columns("task")}
    timeline_columns = {column["name"] for column in sqlalchemy.inspect(engine).get_columns("timelineevent")}
    item_columns = {column["name"] for column in sqlalchemy.inspect(engine).get_columns("sourceitem")}
    assert "resume_command" in harness_columns
    assert "group_id" in task_columns
    assert "client" in timeline_columns and "actor" in timeline_columns
    assert "title_custom" in item_columns

    # The DEFAULT backfills pre-existing rows.
    with engine.connect() as conn:
        row = conn.execute(sqlalchemy.text("SELECT client, actor FROM timelineevent WHERE id='e1'")).one()
        item = conn.execute(sqlalchemy.text("SELECT title_custom FROM sourceitem WHERE id='i1'")).one()
    assert tuple(row) == ("api", "human")
    assert item[0] == 0

    # A second pass is a no-op now that the columns exist.
    db._ensure_columns()


def test_migrate_graph_schedules_to_triggers(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "i.db")
    with engine.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "CREATE TABLE executiongraph "
                "(id VARCHAR PRIMARY KEY, schedule VARCHAR, timezone VARCHAR, enabled BOOLEAN, "
                "next_run_at DATETIME, last_run_at DATETIME)"
            )
        )
        conn.execute(
            sqlalchemy.text(
                "CREATE TABLE graphtrigger "
                "(id VARCHAR PRIMARY KEY, graph_id VARCHAR, type VARCHAR, config VARCHAR, enabled BOOLEAN, "
                "next_run_at DATETIME, last_run_at DATETIME, created_at DATETIME, updated_at DATETIME)"
            )
        )
        conn.execute(
            sqlalchemy.text(
                "INSERT INTO executiongraph (id, schedule, timezone, enabled, next_run_at) "
                "VALUES ('g1', '0 9 * * *', 'Europe/Paris', 1, '2026-11-02 08:00:00')"
            )
        )
        conn.execute(sqlalchemy.text("INSERT INTO executiongraph (id, schedule, enabled) VALUES ('g2', NULL, 0)"))
    monkeypatch.setattr(db, "engine", engine)

    db._migrate_graph_schedules_to_triggers()

    with engine.connect() as conn:
        rows = conn.execute(
            sqlalchemy.text("SELECT graph_id, type, config, enabled FROM graphtrigger ORDER BY graph_id")
        ).all()
        cleared = conn.execute(
            sqlalchemy.text("SELECT schedule, next_run_at, enabled FROM executiongraph WHERE id='g1'")
        ).one()
    # Only the graph with a schedule gets a trigger, carrying its cron and zone.
    assert len(rows) == 1 and rows[0][0] == "g1" and rows[0][1] == "schedule"
    assert '"0 9 * * *"' in rows[0][2] and "Europe/Paris" in rows[0][2] and rows[0][3] == 1
    # The old columns are emptied so the schedule is not read twice.
    assert tuple(cleared) == (None, None, 1)

    # A second pass adds nothing.
    db._migrate_graph_schedules_to_triggers()
    with engine.connect() as conn:
        assert conn.execute(sqlalchemy.text("SELECT count(*) FROM graphtrigger")).scalar() == 1


def test_migrate_graph_triggers_to_nodes_moves_schedules_into_the_definition(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "l.db")
    with engine.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "CREATE TABLE executiongraph "
                "(id VARCHAR PRIMARY KEY, definition VARCHAR, schedule_state VARCHAR, schedule VARCHAR, "
                "timezone VARCHAR, enabled BOOLEAN, next_run_at DATETIME, last_run_at DATETIME)"
            )
        )
        conn.execute(
            sqlalchemy.text(
                "CREATE TABLE graphtrigger "
                "(id VARCHAR PRIMARY KEY, graph_id VARCHAR, type VARCHAR, config VARCHAR, enabled BOOLEAN, "
                "next_run_at DATETIME, last_run_at DATETIME)"
            )
        )
        conn.execute(
            sqlalchemy.text(
                "INSERT INTO executiongraph (id, definition) VALUES "
                '(\'g1\', \'{"nodes": [{"id": "a", "kind": "run", "title": "A"}], "edges": []}\')'
            )
        )
        conn.execute(
            sqlalchemy.text(
                "INSERT INTO graphtrigger (id, graph_id, type, config, enabled, next_run_at) VALUES "
                "('t1', 'g1', 'schedule', '{\"cron\": \"0 9 * * *\", \"timezone\": \"Europe/Paris\"}', 1, "
                "'2026-11-02 08:00:00')"
            )
        )
        conn.execute(
            sqlalchemy.text(
                "INSERT INTO graphtrigger (id, graph_id, type, config, enabled) VALUES "
                "('t2', 'g1', 'webhook', '{\"secret\": \"x\"}', 1)"
            )
        )
    monkeypatch.setattr(db, "engine", engine)

    db._migrate_graph_triggers_to_nodes()

    with engine.connect() as conn:
        definition_raw, state_raw = conn.execute(
            sqlalchemy.text("SELECT definition, schedule_state FROM executiongraph WHERE id='g1'")
        ).one()
        kept = conn.execute(sqlalchemy.text("SELECT count(*) FROM graphtrigger")).scalar()
    definition = json.loads(definition_raw)
    state = json.loads(state_raw)
    trigger = next(node for node in definition["nodes"] if node["id"] != "a")
    assert trigger["kind"] == "trigger" and trigger["triggerType"] == "schedule"
    assert trigger["schedule"] == "0 9 * * *" and trigger["timezone"] == "Europe/Paris"
    # Only the schedule moved; the webhook row is dropped with the table.
    assert kept == 0
    assert state[trigger["id"]]["cron"] == "0 9 * * *"
    assert state[trigger["id"]]["nextRunAt"].startswith("2026-11-02 08:00:00")

    # A second pass adds nothing.
    db._migrate_graph_triggers_to_nodes()
    with engine.connect() as conn:
        definition_raw = conn.execute(sqlalchemy.text("SELECT definition FROM executiongraph WHERE id='g1'")).scalar()
    assert len(json.loads(definition_raw)["nodes"]) == 2


def test_ensure_columns_adds_the_event_subscription_node_id(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "o.db")
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("CREATE TABLE eventsubscription (id VARCHAR PRIMARY KEY)"))
        conn.execute(sqlalchemy.text("INSERT INTO eventsubscription (id) VALUES ('s1')"))
    monkeypatch.setattr(db, "engine", engine)

    db._ensure_columns()

    with engine.connect() as conn:
        assert conn.execute(sqlalchemy.text("SELECT node_id FROM eventsubscription WHERE id='s1'")).scalar() == ""


def test_migrate_graph_triggers_to_nodes_without_tables_is_a_noop(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "m.db")
    monkeypatch.setattr(db, "engine", engine)
    db._migrate_graph_triggers_to_nodes()


def test_ensure_columns_adds_the_graph_schedule_state(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "n.db")
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("CREATE TABLE executiongraph (id VARCHAR PRIMARY KEY)"))
    monkeypatch.setattr(db, "engine", engine)

    db._ensure_columns()

    columns = {column["name"] for column in sqlalchemy.inspect(engine).get_columns("executiongraph")}
    assert "schedule_state" in columns


def test_migrate_graph_schedules_to_triggers_without_tables_is_a_noop(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "j.db")
    monkeypatch.setattr(db, "engine", engine)
    db._migrate_graph_schedules_to_triggers()


def test_ensure_columns_adds_graph_execution_trigger_id(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "k.db")
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text("CREATE TABLE graphexecution (id VARCHAR PRIMARY KEY, graph_id VARCHAR)"))
        conn.execute(sqlalchemy.text("INSERT INTO graphexecution (id, graph_id) VALUES ('x1', 'g1')"))
    monkeypatch.setattr(db, "engine", engine)

    db._ensure_columns()

    with engine.connect() as conn:
        row = conn.execute(sqlalchemy.text("SELECT trigger_id FROM graphexecution WHERE id='x1'")).scalar()
    # The DEFAULT backfills executions recorded before triggers existed.
    assert row == ""


def test_ensure_columns_without_tables_is_a_noop(monkeypatch, tmp_path):
    engine = _engine(tmp_path, "h.db")
    monkeypatch.setattr(db, "engine", engine)
    db._ensure_columns()
