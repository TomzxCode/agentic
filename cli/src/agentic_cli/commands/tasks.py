"""CLI commands."""

from __future__ import annotations

from typing import Literal

from cyclopts import App

from .. import runtime
from ..render import (
    _deps_text,
    _graph_text,
    _join,
    _task_line,
    _task_text,
)
from ..runtime import (
    TaskStatus,
    emit,
    safe,
)

task_app = App(name="task", help="Create and manage tasks.")


def register(app: App) -> None:
    app.command(task_app)
    app.command(name="graph")(graph)


@task_app.command(name="list")
@safe
def task_list(status: TaskStatus | None = None, q: str | None = None, tag: list[str] | None = None) -> str:
    """List tasks, newest first (optionally filtered by --tag, repeatable)."""
    with runtime._client() as client:
        tasks = client.list_tasks(status=status, q=q, tags=tag)
    return emit(tasks, _join(tasks, _task_line))


@task_app.command(name="deadlines")
@safe
def task_deadlines(within_days: int = 7) -> str:
    """List in-flight tasks with a deadline coming up (overdue included)."""
    with runtime._client() as client:
        tasks = client.list_deadlines(within_days=within_days)
    return emit(tasks, _join(tasks, _task_line))


@task_app.command(name="get")
@safe
def task_get(task_id: str) -> str:
    """Show a task with its items, worktrees, runs, and timeline."""
    with runtime._client() as client:
        task = client.get_task(task_id)
    return emit(task, _task_text(task))


@task_app.command(name="create")
@safe
def task_create(
    title: str = "",
    description: str = "",
    priority: int = 2,
    status: TaskStatus = "open",
    tags: list[str] | None = None,
    deadline: str | None = None,
    waiting_on: str | None = None,
    follow_up: str | None = None,
    snooze: str | None = None,
    repository_ids: list[str] | None = None,
    group_id: str | None = None,
    harness_id: str | None = None,
    github_url: str | None = None,
    slack_url: str | None = None,
) -> str:
    """Create a task.

    Import one from a GitHub issue with --github-url, or from a Slack thread
    with --slack-url (an agent then names it and summarizes the discussion).
    Set a deadline with --deadline (an ISO 8601 date or date-time). Park the
    task off the stack with --snooze <when>, or with --waiting-on <person id>
    plus an optional --follow-up <when>.
    """
    with runtime._client() as client:
        task = client.create_task(
            title=title,
            description=description,
            priority=priority,
            status=status,
            tags=tags,
            deadline=deadline,
            waiting_on_person_id=waiting_on,
            follow_up_at=follow_up,
            snoozed_until=snooze,
            repository_ids=repository_ids,
            group_id=group_id,
            harness_id=harness_id,
            github_url=github_url,
            slack_url=slack_url,
        )
    return emit(task, f"created {task['id']}  {task['title']}")


@task_app.command(name="update")
@safe
def task_update(
    task_id: str,
    title: str | None = None,
    description: str | None = None,
    status: TaskStatus | None = None,
    priority: int | None = None,
    tags: list[str] | None = None,
    deadline: str | None = None,
    clear_deadline: bool = False,
    waiting_on: str | None = None,
    follow_up: str | None = None,
    clear_waiting: bool = False,
    snooze: str | None = None,
    clear_snooze: bool = False,
    repository_ids: list[str] | None = None,
    harness_id: str | None = None,
    summary: str | None = None,
) -> str:
    """Update a task's fields.

    Set a deadline with --deadline (an ISO 8601 date or date-time), or remove it
    with --clear-deadline. Park the task with --snooze <when> (--clear-snooze to
    bring it back now), or with --waiting-on <person id> and an optional
    --follow-up <when> (--clear-waiting to stop waiting).
    """
    with runtime._client() as client:
        task = client.update_task(
            task_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            tags=tags,
            deadline=deadline,
            waiting_on_person_id=waiting_on,
            follow_up_at=follow_up,
            snoozed_until=snooze,
            repository_ids=repository_ids,
            harness_id=harness_id,
            summary=summary,
        )
        if clear_deadline:
            task = client.set_task_deadline(task_id, None)
        if clear_waiting:
            task = client.set_task_waiting(task_id, None)
        if clear_snooze:
            task = client.set_task_snooze(task_id, None)
    return emit(task, f"updated {task['id']}  {_task_line(task)}")


@task_app.command(name="delete")
@safe
def task_delete(task_id: str) -> str:
    """Delete a task and everything attached to it."""
    with runtime._client() as client:
        client.delete_task(task_id)
    return emit({"deleted": task_id}, f"deleted {task_id}")


@task_app.command(name="timeline")
@safe
def task_timeline(task_id: str) -> str:
    """Show a task's timeline."""
    with runtime._client() as client:
        events = client.task_timeline(task_id)
    text = _join(events, lambda e: f"{e['created_at'][:19]}  {e['type']:<18} {e['message']}")
    return emit(events, text)


@task_app.command(name="link")
@safe
def task_link(task_id: str, related_id: str, relation: Literal["before", "after"] = "after") -> str:
    """Link a related task before or after this one.

    `--relation before` means the related task must be done first; `after` means
    it follows this one. A link that would close a cycle is refused.
    """
    with runtime._client() as client:
        deps = client.add_dependency(task_id, related_id, relation)
    return emit(deps, _deps_text(deps))


@task_app.command(name="unlink")
@safe
def task_unlink(task_id: str, related_id: str) -> str:
    """Remove the before/after link between two tasks."""
    with runtime._client() as client:
        client.remove_dependency(task_id, related_id)
    return emit({"unlinked": related_id}, f"unlinked {related_id} from {task_id}")


@task_app.command(name="deps")
@safe
def task_deps(task_id: str) -> str:
    """Show the tasks linked before and after this one."""
    with runtime._client() as client:
        deps = client.task_dependencies(task_id)
    return emit(deps, _deps_text(deps))


@safe
def graph(include_done: bool = False) -> str:
    """Show the before/after graph: every task and the edges between them."""
    with runtime._client() as client:
        data = client.get_graph(include_done=include_done)
    return emit(data, _graph_text(data))
