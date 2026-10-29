"""Task mutations: create, update, bulk update, and delete.

Mounted under the same ``/api/tasks`` prefix as the read endpoints; the
shared helpers live in ``task_service``.
"""

from __future__ import annotations

import contextlib
from typing import Any

import anyio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from ..auto_changes import record_merged_pr_changes
from ..checklists import apply_task_templates, delete_task_checklist
from ..crud import add_timeline, field_label, get_task_or_404, jsonable, normalize_tags
from ..db import get_session
from ..events import bus
from ..models.agents import AgentEvent, AgentRun, AgentSession, Harness
from ..models.base import TaskStatus, utcnow
from ..models.changes import Change, ChangeIntervention
from ..models.graphs import GraphExecution
from ..models.items import Association, Person, SourceItem, TaskPerson, TaskRequester
from ..models.repositories import Repository, RepositoryGroup, TaskRepository, Worktree
from ..models.tasks import StackEntry, Task, TaskDependency, TaskRelation, TaskSession, TimelineEvent
from ..schemas.items import ItemCreate
from ..schemas.tasks import (
    TaskBulkDelete,
    TaskBulkDeleteResult,
    TaskBulkResult,
    TaskBulkUpdate,
    TaskCreate,
    TaskRead,
    TaskUpdate,
)
from ..services.git import remove_worktree
from ..services.prompts import SLACK_PLACEHOLDER_TITLE
from .agent_runs import start_slack_summary
from .items import _upsert_item
from .task_service import (
    _link_item,
    _repository_names,
    _set_task_repositories,
    _task_read,
    _task_repository_ids,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# Setting a waiting-on person marks an open task blocked, so "blocked" carries
# who it waits on; clearing the person reopens it. An explicit status in the same
# update wins, and a status the user chose deliberately is left alone.
_WAITING_SOURCE_STATUSES = (TaskStatus.open, TaskStatus.in_progress)


def _waiting_person_id(value: str | None) -> str | None:
    """Normalize an empty selection ("") to no person."""
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _check_waiting_person(session: Session, person_id: str | None) -> None:
    if person_id is not None and session.get(Person, person_id) is None:
        raise HTTPException(status_code=404, detail="Person not found")


def _prepare_waiting(data: dict[str, Any], task: Task | None = None, explicit_status: bool = False) -> None:
    """Validate a waiting-on edit and keep the status and follow-up coherent.

    ``task`` is the row before the edit (None on create). Adding a person to an
    open or in-progress task marks it blocked; removing the person clears the
    follow-up date and reopens a blocked task. A status the request names
    explicitly wins over both rules.
    """
    if "waiting_on_person_id" not in data:
        return
    person_id = _waiting_person_id(data["waiting_on_person_id"])
    data["waiting_on_person_id"] = person_id
    was_waiting = task.waiting_on_person_id if task is not None else None

    if person_id is not None and person_id != was_waiting:
        if not explicit_status and (task is None or task.status in _WAITING_SOURCE_STATUSES):
            data["status"] = TaskStatus.blocked
    elif person_id is None and was_waiting is not None:
        if "follow_up_at" not in data:
            data["follow_up_at"] = None
        if not explicit_status and task is not None and task.status == TaskStatus.blocked:
            data["status"] = TaskStatus.open


@router.post("", response_model=TaskRead, status_code=201)
async def create_task(payload: TaskCreate, session: Session = Depends(get_session)) -> TaskRead:
    data = payload.model_dump(exclude={"github_url", "slack_url", "repository_ids"})
    data["tags"] = normalize_tags(data.get("tags") or [])
    _prepare_waiting(data, explicit_status="status" in payload.model_fields_set)
    _check_waiting_person(session, data.get("waiting_on_person_id"))

    # Import: fetch the source, use it to fill the task, and link it. A Slack
    # import also asks an agent to name the task and summarize the thread.
    item: SourceItem | None = None
    import_source = ""
    slack_import = False
    slack_thread: str | None = None
    if payload.github_url:
        item = await anyio.to_thread.run_sync(_upsert_item, session, ItemCreate(url=payload.github_url, fetch=True))
        data["title"] = data.get("title") or item.title or payload.github_url
        data["description"] = data.get("description") or item.content
        import_source = "GitHub"
    elif payload.slack_url:
        item = await anyio.to_thread.run_sync(_upsert_item, session, ItemCreate(url=payload.slack_url, fetch=True))
        import_source = "Slack"
        slack_import = True
        # slackx runs lazily; an empty fetch (no slackx, not authenticated) still
        # yields an item, but there is nothing for the agent to summarize.
        slack_thread = (item.content or "").strip()
        # The agent names the task, so keep a placeholder until the run finishes.
        if not str(data.get("title") or "").strip():
            data["title"] = item.title if item.title and item.title != item.url else SLACK_PLACEHOLDER_TITLE

    if not str(data.get("title") or "").strip():
        raise HTTPException(status_code=400, detail="Title is required (or provide a github_url or slack_url)")

    task = Task(**data)
    session.add(task)
    session.commit()
    session.refresh(task)

    _set_task_repositories(session, task.id, payload.repository_ids)

    if item is not None:
        _link_item(session, task.id, item, note=f"imported from {import_source}")
        # An imported, already-merged pull request is a landed change.
        record_merged_pr_changes(session, item_ids=[item.id])
        add_timeline(
            session,
            task.id,
            "item_added",
            f"Associated [{item.source}] {item.title or item.url or item.id}",
            {"item_id": item.id},
        )
    # Apply the checklist templates the new task matches, now that its tags,
    # repositories, and any people brought in by an imported item are in place.
    apply_task_templates(session, task)
    add_timeline(session, task.id, "created", f"Task created: {task.title}")
    if slack_import and slack_thread:
        await start_slack_summary(session, task, thread=slack_thread)
    elif slack_import:
        # The thread could not be gathered, so name and summarize nothing.
        add_timeline(
            session,
            task.id,
            "summary_failed",
            "Could not fetch the Slack thread to summarize",
            {"item_id": item.id} if item is not None else {},
        )
    await bus.publish(f"task:{task.id}", {"kind": "task", "action": "created"})
    return _task_read(session, task)


async def _apply_task_update(
    session: Session,
    task: Task,
    data: dict[str, Any],
    repository_ids: list[str] | None = None,
) -> TaskRead:
    """Apply field edits to a task, record the diff, and announce the change.

    Shared by the single-task PATCH and the bulk endpoint so both record the
    same timeline event and SSE notification.
    """
    before = {key: jsonable(getattr(task, key)) for key in data}
    for key, value in data.items():
        setattr(task, key, value)
    task.updated_at = utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)

    # Record the actual before/after for each field that changed (skip no-ops).
    # Relationship fields also carry a resolved label so the timeline reads in
    # names, not ids, for the UI, the CLI, and agents alike.
    relation_models = {"group_id": RepositoryGroup, "harness_id": Harness, "waiting_on_person_id": Person}

    def relation_label(field: str, value: object) -> str | None:
        model = relation_models.get(field)
        if model is None or value in (None, ""):
            return None
        related = session.get(model, value)
        return related.name if related is not None else None

    changes = {}
    for key in data:
        old, new = before[key], jsonable(getattr(task, key))
        if old == new:
            continue
        entry: dict[str, object] = {"from": old, "to": new}
        if key in relation_models:
            entry["from_label"] = relation_label(key, old)
            entry["to_label"] = relation_label(key, new)
        changes[key] = entry

    if repository_ids is not None:
        before_repos = _task_repository_ids(session, task.id)
        _set_task_repositories(session, task.id, repository_ids)
        after_repos = _task_repository_ids(session, task.id)
        if sorted(before_repos) != sorted(after_repos):
            changes["repositories"] = {
                "from": before_repos or None,
                "to": after_repos or None,
                "from_label": ", ".join(_repository_names(session, before_repos)) or None,
                "to_label": ", ".join(_repository_names(session, after_repos)) or None,
            }

    # A rule may match on the field just changed (or on a repository that came
    # with it), so run the templates before returning the fresh read.
    apply_task_templates(session, task)

    if changes and (set(changes) - {"summary", "next_steps"}):
        add_timeline(
            session,
            task.id,
            "updated",
            f"Updated: {', '.join(sorted(field_label(key) for key in changes))}",
            {"changes": changes},
        )
    await bus.publish(f"task:{task.id}", {"kind": "task", "action": "updated"})
    return _task_read(session, task)


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(task_id: str, payload: TaskUpdate, session: Session = Depends(get_session)) -> TaskRead:
    task = get_task_or_404(session, task_id)
    data = payload.model_dump(exclude_unset=True)
    if "tags" in data:
        data["tags"] = normalize_tags(data["tags"] or [])
    _prepare_waiting(data, task, explicit_status="status" in data)
    _check_waiting_person(session, data.get("waiting_on_person_id"))
    repository_ids = data.pop("repository_ids", None)
    return await _apply_task_update(session, task, data, repository_ids)


@router.post("/bulk", response_model=TaskBulkResult)
async def bulk_update_tasks(payload: TaskBulkUpdate, session: Session = Depends(get_session)) -> TaskBulkResult:
    """Apply one status, priority, and/or tag edit to many tasks at once.

    Tags are additive/removable here (unlike PATCH, which replaces the whole
    list), and each task keeps its own timeline entry.
    """
    if not payload.ids:
        raise HTTPException(status_code=400, detail="Provide at least one task id")
    if payload.status is None and payload.priority is None and not payload.add_tags and not payload.remove_tags:
        raise HTTPException(status_code=400, detail="Provide a status, priority, or tag change")

    remove = set(normalize_tags(payload.remove_tags))
    add = normalize_tags(payload.add_tags)

    updated: list[TaskRead] = []
    missing: list[str] = []
    seen: set[str] = set()
    for task_id in payload.ids:
        if task_id in seen:
            continue
        seen.add(task_id)
        task = session.get(Task, task_id)
        if task is None:
            missing.append(task_id)
            continue

        data: dict[str, Any] = {}
        if payload.status is not None and payload.status != task.status:
            data["status"] = payload.status
        if payload.priority is not None and payload.priority != task.priority:
            data["priority"] = payload.priority
        next_tags = normalize_tags([tag for tag in (task.tags or []) if tag not in remove] + add)
        if next_tags != (task.tags or []):
            data["tags"] = next_tags

        if data:
            updated.append(await _apply_task_update(session, task, data))
        else:
            # Matched, but this task already holds the requested state.
            updated.append(_task_read(session, task))

    return TaskBulkResult(updated=updated, missing=missing)


@router.delete("/bulk")
async def bulk_delete_tasks(payload: TaskBulkDelete, session: Session = Depends(get_session)) -> TaskBulkDeleteResult:
    """Delete many tasks at once, skipping ids that no longer exist.

    Each task is removed with the same ordered child cleanup as the single-task
    delete, and each removal is announced on its own.
    """
    if not payload.ids:
        raise HTTPException(status_code=400, detail="Provide at least one task id")

    deleted: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()
    for task_id in payload.ids:
        if task_id in seen:
            continue
        seen.add(task_id)
        task = session.get(Task, task_id)
        if task is None:
            missing.append(task_id)
            continue
        await _delete_task(session, task)
        deleted.append(task_id)

    return TaskBulkDeleteResult(deleted=deleted, missing=missing)


async def _delete_task(session: Session, task: Task) -> None:
    """Remove one task and everything that references it."""
    # Remove worktrees from disk (best effort) before dropping their rows.
    repo_cache: dict[str, Repository] = {}
    for worktree in session.exec(select(Worktree).where(Worktree.task_id == task.id)).all():
        repo = repo_cache.get(worktree.repository_id) or session.get(Repository, worktree.repository_id)
        if repo is not None:
            repo_cache[repo.id] = repo
            with contextlib.suppress(Exception):
                await anyio.to_thread.run_sync(remove_worktree, repo.path, worktree.path)

    # Explicit, ordered deletes: SQLite enforces FKs (PRAGMA foreign_keys=ON),
    # so children must go before the task row.
    run_ids = [r.id for r in session.exec(select(AgentRun).where(AgentRun.task_id == task.id)).all()]
    if run_ids:
        session.exec(sa_delete(AgentEvent).where(col(AgentEvent.run_id).in_(run_ids)))
    session.exec(sa_delete(AgentRun).where(col(AgentRun.task_id) == task.id))
    session.exec(sa_delete(AgentSession).where(col(AgentSession.task_id) == task.id))
    session.exec(sa_delete(Association).where(col(Association.task_id) == task.id))
    # Changes and their interventions belong to the task; drop them before the
    # worktrees they may reference.
    session.exec(
        sa_delete(ChangeIntervention).where(
            col(ChangeIntervention.change_id).in_(select(col(Change.id)).where(col(Change.task_id) == task.id))
        )
    )
    session.exec(sa_delete(Change).where(col(Change.task_id) == task.id))
    session.exec(sa_delete(Worktree).where(col(Worktree.task_id) == task.id))
    session.exec(sa_delete(TimelineEvent).where(col(TimelineEvent.task_id) == task.id))
    session.exec(sa_delete(TaskRepository).where(col(TaskRepository.task_id) == task.id))
    session.exec(sa_delete(TaskPerson).where(col(TaskPerson.task_id) == task.id))
    session.exec(sa_delete(TaskRequester).where(col(TaskRequester.task_id) == task.id))
    # Checklist items and the record of applied templates belong to the task.
    delete_task_checklist(session, task.id)
    # Before/after and related links point at the task from either side; drop
    # them first.
    session.exec(
        sa_delete(TaskDependency).where(
            (col(TaskDependency.before_id) == task.id) | (col(TaskDependency.after_id) == task.id)
        )
    )
    session.exec(
        sa_delete(TaskRelation).where(
            (col(TaskRelation.task_id) == task.id) | (col(TaskRelation.related_id) == task.id)
        )
    )
    # Stack entries (and their sessions) reference the task and must go first.
    entry_ids = [entry.id for entry in session.exec(select(StackEntry).where(StackEntry.task_id == task.id)).all()]
    if entry_ids:
        session.exec(sa_delete(TaskSession).where(col(TaskSession.stack_entry_id).in_(entry_ids)))
    session.exec(sa_delete(StackEntry).where(col(StackEntry.task_id) == task.id))
    # A graph execution keeps the task its run nodes attached to; it has no
    # cascade, so it must go before the task row or SQLite rejects the delete.
    session.exec(sa_delete(GraphExecution).where(col(GraphExecution.task_id) == task.id))
    session.exec(sa_delete(Task).where(col(Task.id) == task.id))
    session.commit()
    await bus.publish("tasks", {"kind": "task", "action": "deleted", "id": task.id})


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str, session: Session = Depends(get_session)) -> None:
    task = get_task_or_404(session, task_id)
    await _delete_task(session, task)
