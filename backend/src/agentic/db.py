"""Database engine and session helpers."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import datetime

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
        checklists,
        graphs,
        items,
        repositories,
        reviews,
        schedules,
        system,
        tasks,
        webhooks,
    )

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.worktree_root.mkdir(parents=True, exist_ok=True)
    _migrate_problem_to_task()
    SQLModel.metadata.create_all(engine)
    _migrate_task_repositories()
    _migrate_person_aliases()
    _migrate_person_notes()
    _migrate_graph_schedules_to_triggers()
    _ensure_columns()
    _migrate_graph_triggers_to_nodes()
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


def _migrate_person_notes() -> None:
    """Move a person's old single notes block into one timestamped note.

    Notes are now separate rows so each keeps its own time. The old column is
    emptied so the text is not shown twice; a fresh database never has text
    there.
    """
    tables = set(inspect(engine).get_table_names())
    if "person" not in tables or "personnote" not in tables:
        return
    columns = {column["name"] for column in inspect(engine).get_columns("person")}
    if "notes" not in columns:
        return
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO personnote (id, person_id, content, created_at, updated_at) "
                "SELECT lower(hex(randomblob(6))), id, notes, "
                "COALESCE(created_at, CURRENT_TIMESTAMP), COALESCE(updated_at, created_at, CURRENT_TIMESTAMP) "
                "FROM person WHERE notes IS NOT NULL AND trim(notes) <> ''"
            )
        )
        connection.execute(text("UPDATE person SET notes = ''"))


def _migrate_graph_schedules_to_triggers() -> None:
    """Turn each graph's old schedule columns into a schedule trigger row.

    A trigger is now its own row, so a cron schedule is one trigger type among
    several instead of a column on the graph. The old columns stay (SQLite
    drops are disruptive) but are emptied, so nothing reads a schedule twice.
    """
    tables = set(inspect(engine).get_table_names())
    if "executiongraph" not in tables or "graphtrigger" not in tables:
        return
    columns = {column["name"] for column in inspect(engine).get_columns("executiongraph")}
    if "schedule" not in columns:
        return
    # `enabled` is as old as the columns around it, but stay tolerant of a
    # schema built before it existed.
    enabled = "COALESCE(g.enabled, 1)" if "enabled" in columns else "1"
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO graphtrigger "
                "(id, graph_id, type, config, enabled, next_run_at, last_run_at, created_at, updated_at) "
                "SELECT lower(hex(randomblob(8))), g.id, 'schedule', "
                "json_object('cron', g.schedule, 'timezone', COALESCE(g.timezone, '')), "
                f"{enabled}, g.next_run_at, g.last_run_at, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
                "FROM executiongraph g "
                "WHERE g.schedule IS NOT NULL AND trim(g.schedule) <> '' "
                "AND NOT EXISTS (SELECT 1 FROM graphtrigger t WHERE t.graph_id = g.id)"
            )
        )
        connection.execute(text("UPDATE executiongraph SET schedule = NULL, timezone = NULL, next_run_at = NULL"))
        if "enabled" in columns:
            # The flag only gated the schedule. The trigger row now carries that
            # pause, so clear it here or webhook deliveries would read the graph
            # as paused with no way to un-pause it.
            connection.execute(text("UPDATE executiongraph SET enabled = 1"))


def _iso(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _migrate_graph_triggers_to_nodes() -> None:
    """Move each graph's schedule trigger rows into schedule trigger nodes.

    A schedule now lives in the graph definition as a trigger node, so the
    scheduler reads the definition and keeps only the derived next occurrence in
    ``executiongraph.schedule_state``. Webhook trigger rows have no node
    equivalent (the Webhooks page owns events now); the table is emptied and
    left in place like the other retired tables.
    """
    tables = set(inspect(engine).get_table_names())
    if "executiongraph" not in tables:
        return
    with engine.begin() as connection:
        graph_rows = connection.execute(
            text(
                "SELECT id, definition, schedule_state, schedule, timezone, enabled, next_run_at, last_run_at "
                "FROM executiongraph"
            )
        ).all()
        trigger_rows = []
        if "graphtrigger" in tables:
            trigger_rows = connection.execute(
                text("SELECT graph_id, type, config, enabled, next_run_at, last_run_at FROM graphtrigger")
            ).all()

        by_graph: dict[str, list[dict]] = {}
        for graph_id, kind, config, enabled, next_run, last_run in trigger_rows:
            if kind != "schedule":
                continue
            parsed = config
            if isinstance(parsed, str):
                try:
                    parsed = json.loads(parsed)
                except ValueError:
                    parsed = {}
            parsed = parsed if isinstance(parsed, dict) else {}
            by_graph.setdefault(graph_id, []).append(
                {
                    "cron": str(parsed.get("cron") or "").strip(),
                    "timezone": str(parsed.get("timezone") or "").strip(),
                    "enabled": bool(enabled),
                    "next": next_run,
                    "last": last_run,
                }
            )

        for (
            graph_id,
            definition_raw,
            state_raw,
            legacy_schedule,
            legacy_timezone,
            legacy_enabled,
            legacy_next,
            legacy_last,
        ) in graph_rows:
            configs = by_graph.get(graph_id, [])
            if not configs and legacy_schedule and str(legacy_schedule).strip():
                configs = [
                    {
                        "cron": str(legacy_schedule).strip(),
                        "timezone": str(legacy_timezone or "").strip(),
                        "enabled": bool(legacy_enabled),
                        "next": legacy_next,
                        "last": legacy_last,
                    }
                ]
            if not configs:
                continue

            definition = definition_raw
            if isinstance(definition, str):
                try:
                    definition = json.loads(definition)
                except ValueError:
                    definition = {}
            definition = definition if isinstance(definition, dict) else {}
            state = state_raw
            if isinstance(state, str):
                try:
                    state = json.loads(state)
                except ValueError:
                    state = {}
            state = state if isinstance(state, dict) else {}

            nodes = list(definition.get("nodes") or [])
            titles = {str(node.get("title") or "") for node in nodes}
            existing = {
                (str(node.get("schedule") or ""), str(node.get("timezone") or ""))
                for node in nodes
                if node.get("kind") == "trigger" and node.get("triggerType") == "schedule"
            }
            base_y = max([float((node.get("position") or {}).get("y") or 0) for node in nodes] or [0.0]) + 120
            changed = False
            for index, config in enumerate(configs):
                cron, zone = str(config["cron"]), str(config["timezone"])
                if not cron or (cron, zone) in existing:
                    continue
                title = "Schedule"
                suffix = 2
                while title in titles:
                    title = f"Schedule {suffix}"
                    suffix += 1
                node_id = f"n{uuid.uuid4().hex[:12]}"
                nodes.append(
                    {
                        "id": node_id,
                        "kind": "trigger",
                        "triggerType": "schedule",
                        "title": title,
                        "position": {"x": 40.0, "y": base_y + index * 120.0},
                        "schedule": cron,
                        "timezone": zone,
                        "enabled": bool(config["enabled"]),
                        "outputs": [],
                    }
                )
                titles.add(title)
                existing.add((cron, zone))
                changed = True
                if config["enabled"] and config["next"] is not None:
                    state[node_id] = {
                        "nextRunAt": _iso(config["next"]),
                        "lastRunAt": _iso(config["last"]),
                        "cron": cron,
                        "timezone": zone,
                    }

            if changed:
                definition["nodes"] = nodes
                connection.execute(
                    text("UPDATE executiongraph SET definition = :definition, schedule_state = :state WHERE id = :id"),
                    {"definition": json.dumps(definition), "state": json.dumps(state), "id": graph_id},
                )

        if "graphtrigger" in tables:
            connection.execute(text("DELETE FROM graphtrigger"))


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
        if "requested_model" not in run_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE agentrun ADD COLUMN requested_model VARCHAR"))
        if "model_name" not in run_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE agentrun ADD COLUMN model_name VARCHAR"))
        if "graph_execution_id" not in run_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE agentrun ADD COLUMN graph_execution_id VARCHAR"))
                connection.execute(text("CREATE INDEX ix_agentrun_graph_execution_id ON agentrun (graph_execution_id)"))
        if "graph_node_id" not in run_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE agentrun ADD COLUMN graph_node_id VARCHAR"))
    if "task" in inspector.get_table_names():
        task_columns = {column["name"] for column in inspector.get_columns("task")}
        if "group_id" not in task_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE task ADD COLUMN group_id VARCHAR"))
        if "deadline" not in task_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE task ADD COLUMN deadline DATETIME"))
        if "waiting_on_person_id" not in task_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE task ADD COLUMN waiting_on_person_id VARCHAR"))
        if "follow_up_at" not in task_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE task ADD COLUMN follow_up_at DATETIME"))
        if "snoozed_until" not in task_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE task ADD COLUMN snoozed_until DATETIME"))
    if "stackentry" in inspector.get_table_names():
        entry_columns = {column["name"] for column in inspector.get_columns("stackentry")}
        if "deleted_reason" not in entry_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE stackentry ADD COLUMN deleted_reason VARCHAR"))
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
        if "done_at" not in item_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE sourceitem ADD COLUMN done_at DATETIME"))
        if "done_message_ts" not in item_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE sourceitem ADD COLUMN done_message_ts VARCHAR"))
    if "reviewrequest" in inspector.get_table_names():
        request_columns = {column["name"] for column in inspector.get_columns("reviewrequest")}
        if "review_scope" not in request_columns:
            with engine.begin() as connection:
                # Rows stored before the scope existed belong to the personal
                # queue; the next scan writes the team flag it finds.
                connection.execute(
                    text("ALTER TABLE reviewrequest ADD COLUMN review_scope VARCHAR NOT NULL DEFAULT 'me'")
                )
    if "repository" in inspector.get_table_names():
        repository_columns = {column["name"] for column in inspector.get_columns("repository")}
        if "review_scan" not in repository_columns:
            with engine.begin() as connection:
                # DEFAULT backfills existing repositories to follow the app-wide
                # setting rather than each needing an explicit opinion.
                connection.execute(
                    text("ALTER TABLE repository ADD COLUMN review_scan VARCHAR NOT NULL DEFAULT 'default'")
                )
    if "reviewrequest" in inspector.get_table_names():
        request_columns = {column["name"] for column in inspector.get_columns("reviewrequest")}
        if "ready_for_review_at" not in request_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE reviewrequest ADD COLUMN ready_for_review_at DATETIME"))
    if "executiongraph" in inspector.get_table_names():
        graph_columns = {column["name"] for column in inspector.get_columns("executiongraph")}
        if "schedule_state" not in graph_columns:
            with engine.begin() as connection:
                # Derived from the definition's schedule trigger nodes.
                connection.execute(text("ALTER TABLE executiongraph ADD COLUMN schedule_state JSON"))
    if "graphexecution" in inspector.get_table_names():
        execution_columns = {column["name"] for column in inspector.get_columns("graphexecution")}
        if "trigger_id" not in execution_columns:
            with engine.begin() as connection:
                # DEFAULT backfills executions recorded before triggers existed.
                connection.execute(text("ALTER TABLE graphexecution ADD COLUMN trigger_id VARCHAR NOT NULL DEFAULT ''"))
    if "eventsubscription" in inspector.get_table_names():
        subscription_columns = {column["name"] for column in inspector.get_columns("eventsubscription")}
        if "node_id" not in subscription_columns:
            with engine.begin() as connection:
                # DEFAULT backfills hand-wired subscriptions from before the
                # event trigger node owned one.
                connection.execute(text("ALTER TABLE eventsubscription ADD COLUMN node_id VARCHAR NOT NULL DEFAULT ''"))
    if "scheduledtask" in inspector.get_table_names():
        schedule_columns = {column["name"] for column in inspector.get_columns("scheduledtask")}
        if "timezone" not in schedule_columns:
            with engine.begin() as connection:
                # NULL means the task follows the server's timezone.
                connection.execute(text("ALTER TABLE scheduledtask ADD COLUMN timezone VARCHAR"))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
