"""Tasks: the unit of work everything else hangs off."""

from __future__ import annotations

import contextlib

import anyio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, select

from ..crud import add_timeline, field_label, get_task_or_404, jsonable
from ..db import get_session
from ..events import bus
from ..links import run_read
from ..models import (
    AgentEvent,
    AgentRun,
    Association,
    Harness,
    Repository,
    RepositoryGroup,
    SourceItem,
    Task,
    TimelineEvent,
    Worktree,
    utcnow,
)
from ..schemas import (
    AssociateRequest,
    AssociationDetail,
    ItemRead,
    TaskCreate,
    TaskDetail,
    TaskRead,
    TaskUpdate,
    TimelineRead,
    WorktreeRead,
)
from ..services import remove_worktree
from .items import _upsert_item

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _detail(session: Session, task: Task) -> TaskDetail:
    associations = session.exec(
        select(Association).where(Association.task_id == task.id).order_by(Association.created_at.desc())
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
        select(Worktree).where(Worktree.task_id == task.id).order_by(Worktree.created_at.desc())
    ).all()
    runs = session.exec(
        select(AgentRun).where(AgentRun.task_id == task.id).order_by(AgentRun.created_at.desc()).limit(20)
    ).all()
    timeline = session.exec(
        select(TimelineEvent)
        .where(TimelineEvent.task_id == task.id)
        .order_by(TimelineEvent.created_at.desc())
        .limit(100)
    ).all()
    return TaskDetail(
        **TaskRead.model_validate(task).model_dump(),
        associations=details,
        worktrees=[WorktreeRead.model_validate(w) for w in worktrees],
        runs=[run_read(session, r) for r in runs],
        timeline=[TimelineRead.model_validate(t) for t in timeline],
    )


@router.get("", response_model=list[TaskRead])
def list_tasks(
    status: str | None = None,
    q: str | None = None,
    session: Session = Depends(get_session),
) -> list[Task]:
    query = select(Task).order_by(Task.updated_at.desc())
    if status:
        query = query.where(Task.status == status)
    tasks = list(session.exec(query).all())
    if q:
        needle = q.lower()
        tasks = [
            p
            for p in tasks
            if needle in p.title.lower()
            or needle in (p.description or "").lower()
            or needle in (p.summary or "").lower()
        ]
    return tasks


@router.post("", response_model=TaskRead, status_code=201)
async def create_task(payload: TaskCreate, session: Session = Depends(get_session)) -> Task:
    task = Task(**payload.model_dump())
    session.add(task)
    session.commit()
    session.refresh(task)
    add_timeline(session, task.id, "created", f"Task created: {task.title}")
    await bus.publish(f"task:{task.id}", {"kind": "task", "action": "created"})
    return task


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(task_id: str, session: Session = Depends(get_session)) -> TaskDetail:
    task = get_task_or_404(session, task_id)
    return _detail(session, task)


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(task_id: str, payload: TaskUpdate, session: Session = Depends(get_session)) -> Task:
    task = get_task_or_404(session, task_id)
    data = payload.model_dump(exclude_unset=True)
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
    relation_models = {"repository_id": Repository, "group_id": RepositoryGroup, "harness_id": Harness}

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
    if changes and (set(changes) - {"summary", "next_steps"}):
        add_timeline(
            session,
            task.id,
            "updated",
            f"Updated: {', '.join(sorted(field_label(key) for key in changes))}",
            {"changes": changes},
        )
    await bus.publish(f"task:{task.id}", {"kind": "task", "action": "updated"})
    return task


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
        session.execute(sa_delete(AgentEvent).where(AgentEvent.run_id.in_(run_ids)))
    session.execute(sa_delete(AgentRun).where(AgentRun.task_id == task.id))
    session.execute(sa_delete(Association).where(Association.task_id == task.id))
    session.execute(sa_delete(Worktree).where(Worktree.task_id == task.id))
    session.execute(sa_delete(TimelineEvent).where(TimelineEvent.task_id == task.id))
    session.execute(sa_delete(Task).where(Task.id == task.id))
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

    existing = session.exec(
        select(Association).where(Association.task_id == task_id, Association.item_id == item.id)
    ).first()
    assoc = existing or Association(task_id=task_id, item_id=item.id, note=payload.note)
    if existing:
        assoc.note = payload.note or assoc.note
    session.add(assoc)
    session.commit()
    session.refresh(assoc)
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
            select(TimelineEvent).where(TimelineEvent.task_id == task_id).order_by(TimelineEvent.created_at.desc())
        ).all()
    )


__all__ = ["router", "_detail"]
