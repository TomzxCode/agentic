"""The focus stack: an ordered queue of tasks with the current one on top."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from .. import stack as service
from ..crud import get_task_or_404
from ..db import get_session
from ..models.base import utcnow
from ..models.tasks import StackEntry, Task, TaskSession
from ..schemas.stack import StackEntryRead, StackEntryUpdate, StackPush, StackReorder
from .task_service import _task_read, _task_reads

router = APIRouter(prefix="/api/stack", tags=["stack"])


def _read(session: Session, entry: StackEntry) -> StackEntryRead:
    task = session.get(Task, entry.task_id)
    return StackEntryRead(
        id=entry.id,
        task_id=entry.task_id,
        task=_task_read(session, task) if task is not None else None,
        position=entry.position,
        is_current=entry.is_current,
        created_at=entry.created_at,
        deleted_at=entry.deleted_at,
        **service.entry_stats(session, entry),
    )


def _read_all(session: Session, entries: list[StackEntry]) -> list[StackEntryRead]:
    task_ids = [entry.task_id for entry in entries if entry.task_id]
    tasks_by_id = {}
    if task_ids:
        for task in session.exec(select(Task).where(Task.id.in_(task_ids))).all():
            tasks_by_id[task.id] = task
    task_reads = _task_reads(session, [tasks_by_id[tid] for tid in task_ids if tid in tasks_by_id])
    task_read_by_id = {read.id: read for read in task_reads}

    entry_ids = [entry.id for entry in entries]
    sessions_by_entry: dict[str, list[TaskSession]] = {entry_id: [] for entry_id in entry_ids}
    if entry_ids:
        for stint in session.exec(
            select(TaskSession).where(TaskSession.stack_entry_id.in_(entry_ids)).order_by(col(TaskSession.started_at))
        ).all():
            sessions_by_entry.setdefault(stint.stack_entry_id, []).append(stint)

    now = utcnow()
    result: list[StackEntryRead] = []
    for entry in entries:
        task = tasks_by_id.get(entry.task_id) if entry.task_id else None
        task_read = task_read_by_id.get(entry.task_id) if entry.task_id else None
        stats = service._entry_stats_from_sessions(sessions_by_entry.get(entry.id, []), now)
        result.append(
            StackEntryRead(
                id=entry.id,
                task_id=entry.task_id,
                task=task_read,
                position=entry.position,
                is_current=entry.is_current,
                created_at=entry.created_at,
                deleted_at=entry.deleted_at,
                **stats,
            )
        )
    return result


@router.get("", response_model=list[StackEntryRead])
def list_stack(session: Session = Depends(get_session)) -> list[StackEntryRead]:
    """The stack, current task first. In-flight tasks join it automatically."""
    return _read_all(session, service.sync_stack(session))


@router.get("/history", response_model=list[StackEntryRead])
def stack_history(session: Session = Depends(get_session)) -> list[StackEntryRead]:
    """Soft-deleted entries, most recently removed first."""
    return _read_all(session, service.history_entries(session))


@router.get("/current", response_model=StackEntryRead | None)
def stack_current(session: Session = Depends(get_session)) -> StackEntryRead | None:
    """The current task, or null when the stack is empty."""
    service.sync_stack(session)
    entry = service.current_entry(session)
    return _read(session, entry) if entry is not None else None


@router.post("", response_model=list[StackEntryRead], status_code=201)
def push_stack(payload: StackPush, session: Session = Depends(get_session)) -> list[StackEntryRead]:
    """Add a task to the stack (top, next, or last) and return the new stack."""
    service.sync_stack(session)
    if payload.task_id:
        task = get_task_or_404(session, payload.task_id)
        if any(entry.task_id == task.id for entry in service.active_entries(session)):
            raise HTTPException(status_code=409, detail="Task is already on the stack")
        entries = service.push(session, position=payload.position, task=task)
    else:
        if not payload.title.strip():
            raise HTTPException(status_code=400, detail="Title is required (or provide a task_id)")
        entries = service.push(session, title=payload.title, description=payload.description, position=payload.position)
    return _read_all(session, entries)


@router.post("/pop", response_model=list[StackEntryRead])
def pop_stack(session: Session = Depends(get_session)) -> list[StackEntryRead]:
    """Pop the current task (mark it done) and return the new stack."""
    service.sync_stack(session)
    return _read_all(session, service.pop(session))


@router.post("/reorder", response_model=list[StackEntryRead])
def reorder_stack(payload: StackReorder, session: Session = Depends(get_session)) -> list[StackEntryRead]:
    """Move an entry to a new position and return the new stack."""
    service.sync_stack(session)
    return _read_all(session, service.reorder(session, payload.entry_id, payload.position))


@router.post("/{entry_id}/promote", response_model=list[StackEntryRead])
def promote_stack(entry_id: str, session: Session = Depends(get_session)) -> list[StackEntryRead]:
    """Move an entry to the top of the stack and return the new stack."""
    service.sync_stack(session)
    return _read_all(session, service.promote(session, entry_id))


@router.patch("/{entry_id}", response_model=list[StackEntryRead])
def update_stack_entry(
    entry_id: str, payload: StackEntryUpdate, session: Session = Depends(get_session)
) -> list[StackEntryRead]:
    """Edit the task behind an entry (title and/or description)."""
    service.sync_stack(session)
    data = payload.model_dump(exclude_unset=True)
    return _read_all(session, service.update_entry(session, entry_id, **data))


@router.delete("/{entry_id}", status_code=204)
def remove_stack_entry(entry_id: str, session: Session = Depends(get_session)) -> None:
    """Remove an entry from the stack (soft delete; the task is kept)."""
    service.sync_stack(session)
    if not any(entry.id == entry_id for entry in service.active_entries(session)):
        raise HTTPException(status_code=404, detail="Stack entry not found")
    service.remove(session, entry_id)


__all__ = ["router"]
