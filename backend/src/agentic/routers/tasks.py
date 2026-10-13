"""Tasks: the unit of work everything else hangs off."""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import Any

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from ..crud import add_timeline, field_label, get_task_or_404, jsonable, normalize_tags
from ..db import get_session
from ..events import bus
from ..links import run_read
from ..models import (
    AgentEvent,
    AgentRun,
    Association,
    Change,
    ChangeIntervention,
    Harness,
    Repository,
    RepositoryGroup,
    SourceItem,
    Task,
    TaskPerson,
    TaskRepository,
    TaskStatus,
    TimelineEvent,
    Worktree,
    WorktreeStatus,
    utcnow,
)
from ..schemas import (
    AssociateRequest,
    AssociationDetail,
    ChangeRead,
    ItemCreate,
    ItemRead,
    TaskBulkResult,
    TaskBulkUpdate,
    TaskCreate,
    TaskDetail,
    TaskRead,
    TaskUpdate,
    TimelineRead,
    WorktreeRead,
)
from ..services import SLACK_PLACEHOLDER_TITLE, github_owner_repo, remove_worktree
from .agents import start_slack_summary
from .items import _upsert_item
from .people import _person_read, link_item_people_to_task, task_people, task_person_ids

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _task_repository_ids(session: Session, task_id: str) -> list[str]:
    return [
        member.repository_id
        for member in session.exec(
            select(TaskRepository).where(TaskRepository.task_id == task_id).order_by(col(TaskRepository.created_at))
        ).all()
    ]


def _set_task_repositories(session: Session, task_id: str, repository_ids: list[str]) -> None:
    session.exec(sa_delete(TaskRepository).where(col(TaskRepository.task_id) == task_id))
    seen: set[str] = set()
    for repository_id in repository_ids:
        if repository_id in seen or session.get(Repository, repository_id) is None:
            continue
        seen.add(repository_id)
        session.add(TaskRepository(task_id=task_id, repository_id=repository_id))
    session.commit()


def _repository_for_item(session: Session, item: SourceItem) -> Repository | None:
    """The repository a source item belongs to, matched by its GitHub owner/repo.

    GitHub issue and PR links carry the repository they live in, so a task that
    tracks one can be pointed at the matching local checkout automatically.
    """
    if item.source != "github":
        return None
    target = github_owner_repo(item.url)
    if target is None:
        return None
    wanted = (target[0].lower(), target[1].lower())
    for repository in session.exec(select(Repository)).all():
        remote = github_owner_repo(repository.remote_url)
        if remote and (remote[0].lower(), remote[1].lower()) == wanted:
            return repository
    return None


def _link_repository_for_item(session: Session, task_id: str, item: SourceItem) -> Repository | None:
    """Attach the item's repository to the task (idempotent) when it matches one."""
    repository = _repository_for_item(session, item)
    if repository is None:
        return None
    existing = session.exec(
        select(TaskRepository).where(TaskRepository.task_id == task_id, TaskRepository.repository_id == repository.id)
    ).first()
    if existing is None:
        session.add(TaskRepository(task_id=task_id, repository_id=repository.id))
        session.commit()
    return repository


def _task_read(session: Session, task: Task) -> TaskRead:
    data = TaskRead.model_validate(task)
    data.repository_ids = _task_repository_ids(session, task.id)
    data.person_ids = task_person_ids(session, task.id)
    return data


def _repository_names(session: Session, repository_ids: list[str]) -> list[str]:
    return [repo.name for repo in (session.get(Repository, rid) for rid in repository_ids) if repo is not None]


def _detail(session: Session, task: Task) -> TaskDetail:
    associations = session.exec(
        select(Association).where(Association.task_id == task.id).order_by(col(Association.created_at).desc())
    ).all()
    details: list[AssociationDetail] = []
    for assoc in associations:
        item = session.get(SourceItem, assoc.item_id)
        if item is None:
            continue
        details.append(
            AssociationDetail(
                id=assoc.id,
                note=assoc.note,
                created_at=assoc.created_at,
                item=ItemRead.model_validate(item),
            )
        )
    worktrees = session.exec(
        select(Worktree)
        .where(Worktree.task_id == task.id)
        .order_by(
            case((col(Worktree.status) == WorktreeStatus.active, 0), else_=1),
            col(Worktree.created_at).desc(),
        )
    ).all()
    runs = session.exec(
        select(AgentRun).where(AgentRun.task_id == task.id).order_by(col(AgentRun.created_at).desc()).limit(20)
    ).all()
    changes = session.exec(
        select(Change).where(Change.task_id == task.id).order_by(col(Change.opened_at).desc()).limit(100)
    ).all()
    timeline = session.exec(
        select(TimelineEvent)
        .where(TimelineEvent.task_id == task.id)
        .order_by(col(TimelineEvent.created_at).desc())
        .limit(100)
    ).all()
    return TaskDetail(
        **_task_read(session, task).model_dump(),
        associations=details,
        people=[_person_read(session, person) for person in task_people(session, task.id)],
        worktrees=[WorktreeRead.model_validate(w) for w in worktrees],
        runs=[run_read(session, r) for r in runs],
        changes=[ChangeRead.model_validate(c) for c in changes],
        timeline=[TimelineRead.model_validate(t) for t in timeline],
    )


def _link_item(session: Session, task_id: str, item: SourceItem, note: str = "") -> Association:
    """Create (or update) the association between a task and an item."""
    existing = session.exec(
        select(Association).where(Association.task_id == task_id, Association.item_id == item.id)
    ).first()
    assoc = existing or Association(task_id=task_id, item_id=item.id, note=note)
    if existing and note:
        assoc.note = note
    session.add(assoc)
    session.commit()
    session.refresh(assoc)
    # A linked source brings its people: everyone already on the item joins the task.
    link_item_people_to_task(session, task_id, item.id)
    # A linked GitHub issue or PR also brings its repository, when it is known.
    _link_repository_for_item(session, task_id, item)
    return assoc


@router.get("", response_model=list[TaskRead])
def list_tasks(
    status: str | None = None,
    q: str | None = None,
    tag: list[str] = Query(default=[]),
    session: Session = Depends(get_session),
) -> list[TaskRead]:
    query = select(Task).order_by(col(Task.updated_at).desc())
    if status:
        query = query.where(Task.status == status)
    tasks = list(session.exec(query).all())
    # A task matches only when it carries every requested tag (AND).
    wanted = set(normalize_tags(tag))
    if wanted:
        tasks = [p for p in tasks if wanted.issubset(set(p.tags or []))]
    if q:
        needle = q.lower()
        tasks = [
            p
            for p in tasks
            if needle in p.title.lower()
            or needle in (p.description or "").lower()
            or needle in (p.summary or "").lower()
        ]
    return [_task_read(session, task) for task in tasks]


# Declared before /{task_id} so "deadlines" is not read as a task id.
@router.get("/deadlines", response_model=list[TaskRead])
def list_deadlines(within_days: int = 7, session: Session = Depends(get_session)) -> list[TaskRead]:
    """In-flight tasks with a deadline, soonest first (overdue included).

    A task is included when its deadline is at or before now plus ``within_days``;
    overdue deadlines always match, since those need attention most.
    """
    cutoff = utcnow() + timedelta(days=max(0, within_days))
    tasks = session.exec(
        select(Task)
        .where(col(Task.deadline).is_not(None))
        .where(col(Task.deadline) <= cutoff)
        .order_by(col(Task.deadline))
    ).all()
    closed = (TaskStatus.done, TaskStatus.archived)
    return [_task_read(session, task) for task in tasks if task.status not in closed]


@router.post("", response_model=TaskRead, status_code=201)
async def create_task(payload: TaskCreate, session: Session = Depends(get_session)) -> TaskRead:
    data = payload.model_dump(exclude={"github_url", "slack_url", "repository_ids"})
    data["tags"] = normalize_tags(data.get("tags") or [])

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
        add_timeline(
            session,
            task.id,
            "item_added",
            f"Associated [{item.source}] {item.title or item.url or item.id}",
            {"item_id": item.id},
        )
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


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(task_id: str, session: Session = Depends(get_session)) -> TaskDetail:
    task = get_task_or_404(session, task_id)
    return _detail(session, task)


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
    relation_models = {"group_id": RepositoryGroup, "harness_id": Harness}

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
    repository_ids = data.pop("repository_ids", None)
    return await _apply_task_update(session, task, data, repository_ids)


@router.post("/bulk", response_model=TaskBulkResult)
async def bulk_update_tasks(payload: TaskBulkUpdate, session: Session = Depends(get_session)) -> TaskBulkResult:
    """Apply one status and/or tag edit to many tasks at once.

    Tags are additive/removable here (unlike PATCH, which replaces the whole
    list), and each task keeps its own timeline entry.
    """
    if not payload.ids:
        raise HTTPException(status_code=400, detail="Provide at least one task id")
    if payload.status is None and not payload.add_tags and not payload.remove_tags:
        raise HTTPException(status_code=400, detail="Provide a status or a tag change")

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
        next_tags = normalize_tags([tag for tag in (task.tags or []) if tag not in remove] + add)
        if next_tags != (task.tags or []):
            data["tags"] = next_tags

        if data:
            updated.append(await _apply_task_update(session, task, data))
        else:
            # Matched, but this task already holds the requested state.
            updated.append(_task_read(session, task))

    return TaskBulkResult(updated=updated, missing=missing)


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str, session: Session = Depends(get_session)) -> None:
    task = get_task_or_404(session, task_id)

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
    session.exec(sa_delete(Task).where(col(Task.id) == task.id))
    session.commit()
    await bus.publish("tasks", {"kind": "task", "action": "deleted", "id": task_id})


@router.post("/{task_id}/items", response_model=AssociationDetail, status_code=201)
async def associate_item(
    task_id: str, payload: AssociateRequest, session: Session = Depends(get_session)
) -> AssociationDetail:
    get_task_or_404(session, task_id)
    if payload.item is not None:
        # Fetching (network/CLI) happens here; keep it off the event loop.
        item = await anyio.to_thread.run_sync(_upsert_item, session, payload.item)
    elif payload.item_id is not None:
        item = session.get(SourceItem, payload.item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Item not found")
    else:
        raise HTTPException(status_code=400, detail="Provide item_id or item")

    assoc = _link_item(session, task_id, item, payload.note)
    add_timeline(
        session,
        task_id,
        "item_added",
        f"Associated [{item.source}] {item.title or item.url or item.id}",
        {"item_id": item.id},
    )
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "items_changed"})
    return AssociationDetail(
        id=assoc.id, note=assoc.note, created_at=assoc.created_at, item=ItemRead.model_validate(item)
    )


@router.delete("/{task_id}/items/{item_id}", status_code=204)
async def unassociate_item(task_id: str, item_id: str, session: Session = Depends(get_session)) -> None:
    assoc = session.exec(
        select(Association).where(Association.task_id == task_id, Association.item_id == item_id)
    ).first()
    if assoc is None:
        raise HTTPException(status_code=404, detail="Association not found")
    session.delete(assoc)
    session.commit()
    add_timeline(session, task_id, "item_removed", "Item unassociated", {"item_id": item_id})
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "items_changed"})


@router.get("/{task_id}/timeline", response_model=list[TimelineRead])
def get_timeline(task_id: str, session: Session = Depends(get_session)) -> list[TimelineEvent]:
    get_task_or_404(session, task_id)
    return list(
        session.exec(
            select(TimelineEvent).where(TimelineEvent.task_id == task_id).order_by(col(TimelineEvent.created_at).desc())
        ).all()
    )


__all__ = ["router", "_detail"]
