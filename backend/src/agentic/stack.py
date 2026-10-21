"""The focus stack: an ordered list of tasks with the current one on top.

This is task-stack's model re-implemented on Agentic's tasks. A task's presence
on the stack is a ``StackEntry``; position 0 is the current task and the rest
are queued. Each stretch of time an entry spends as current is a ``TaskSession``,
from which ``execution_count`` and ``duration`` are derived. Popping or removing
an entry soft-deletes it, so the stack keeps a history.

The stack is materialized from the in-flight tasks: every task that is open, in
progress, or blocked and has never been on the stack joins it at the bottom, so
you never have to add work by hand. A task you popped or removed keeps its
soft-deleted entry and is not re-added until you push it again.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict, overload

from sqlalchemy import or_
from sqlmodel import Session, col, select

from .crud import add_timeline
from .models.base import TaskStatus, utcnow
from .models.tasks import StackEntry, Task, TaskSession

# The statuses that belong on the stack. A task in any other status (done or
# archived) is not in flight and does not belong on it.
IN_FLIGHT_STATUSES = (TaskStatus.open, TaskStatus.in_progress, TaskStatus.blocked)


class EntryStats(TypedDict):
    """Session-derived stats for one stack entry."""

    started_at: datetime | None
    last_current: datetime | None
    duration: float
    execution_count: int


@overload
def _as_utc(value: datetime) -> datetime: ...


@overload
def _as_utc(value: None) -> None: ...


def _as_utc(value: datetime | None) -> datetime | None:
    """Treat a naive datetime read back from SQLite as UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def parked_reason(task: Task, now: datetime) -> str | None:
    """Why a task is off the stack right now, or None when it belongs on it.

    A snooze parks the task until its date. A waiting task parks until its
    follow-up date, or indefinitely when no follow-up is set, so it only comes
    back when the person is cleared or the task is pushed by hand.
    """
    snoozed_until = _as_utc(task.snoozed_until)
    if snoozed_until is not None and snoozed_until > now:
        return "snoozed"
    if task.waiting_on_person_id:
        follow_up_at = _as_utc(task.follow_up_at)
        if follow_up_at is None or follow_up_at > now:
            return "waiting"
    return None


def is_parked(task: Task, now: datetime) -> bool:
    return parked_reason(task, now) is not None


def active_entries(session: Session) -> list[StackEntry]:
    """The stack, current task first, soft-deleted entries excluded."""
    return list(
        session.exec(
            select(StackEntry).where(col(StackEntry.deleted_at).is_(None)).order_by(col(StackEntry.position))
        ).all()
    )


def history_entries(session: Session) -> list[StackEntry]:
    """The soft-deleted history, most recently removed first.

    Parked entries are left out: a waiting or snoozed task is still in flight,
    it is only off the stack until its date, so it is not "removed".
    """
    return list(
        session.exec(
            select(StackEntry)
            .where(col(StackEntry.deleted_at).is_not(None))
            .where(or_(col(StackEntry.deleted_reason).is_(None), col(StackEntry.deleted_reason) != "parked"))
            .order_by(col(StackEntry.deleted_at).desc())
        ).all()
    )


def sessions_for(session: Session, entry_id: str) -> list[TaskSession]:
    return list(
        session.exec(
            select(TaskSession).where(TaskSession.stack_entry_id == entry_id).order_by(col(TaskSession.started_at))
        ).all()
    )


def entry_stats(session: Session, entry: StackEntry, now: datetime | None = None) -> EntryStats:
    """Derive an entry's session stats: started_at, last_current, duration, count."""
    now = now or utcnow()
    sessions = sessions_for(session, entry.id)
    started_at = _as_utc(sessions[0].started_at) if sessions else None
    last = sessions[-1] if sessions else None
    last_current = None
    if last is not None:
        last_current = _as_utc(last.ended_at) if last.ended_at is not None else _as_utc(last.started_at)

    duration = 0.0
    for stint in sessions:
        if stint.ended_at is None:
            continue
        elapsed = (_as_utc(stint.ended_at) - _as_utc(stint.started_at)).total_seconds()
        if elapsed > 0:
            duration += elapsed
    # A session still open (the current task) counts toward the live duration.
    if last is not None and last.ended_at is None:
        elapsed = (now - _as_utc(last.started_at)).total_seconds()
        if elapsed > 0:
            duration += elapsed

    return {
        "started_at": started_at,
        "last_current": last_current,
        "duration": duration,
        "execution_count": len(sessions),
    }


def _close_open_session(session: Session, entry: StackEntry, now: datetime) -> None:
    open_session = session.exec(
        select(TaskSession)
        .where(TaskSession.stack_entry_id == entry.id)
        .where(col(TaskSession.ended_at).is_(None))
        .order_by(col(TaskSession.started_at).desc())
    ).first()
    if open_session is not None:
        open_session.ended_at = now
        session.add(open_session)


def _reindex(session: Session, entries: list[StackEntry]) -> None:
    for position, entry in enumerate(entries):
        if entry.position != position:
            entry.position = position
            session.add(entry)


def _set_current(session: Session, entries: list[StackEntry], now: datetime) -> None:
    """Flag the head as current (opening its session) and close everyone else's."""
    head_id = entries[0].id if entries else None
    for entry in entries:
        if entry.id == head_id:
            if not entry.is_current:
                entry.is_current = True
                session.add(entry)
                _close_open_session(session, entry, now)
                session.add(TaskSession(stack_entry_id=entry.id, started_at=now))
        elif entry.is_current:
            entry.is_current = False
            session.add(entry)
            _close_open_session(session, entry, now)


def _soft_delete(session: Session, entry: StackEntry, now: datetime, reason: str | None = None) -> None:
    entry.is_current = False
    entry.deleted_at = now
    entry.deleted_reason = reason
    session.add(entry)
    _close_open_session(session, entry, now)


def sync_stack(session: Session, now: datetime | None = None) -> list[StackEntry]:
    """Materialize the stack from the in-flight tasks.

    Every task that is open, in progress, or blocked, is not parked, and has
    never had a stack entry joins at the bottom. An entry leaves when its task
    is no longer in flight or becomes parked (waiting or snoozed). A task that
    was popped or removed keeps its (soft-deleted) entry and is not re-added;
    a task whose last entry was deleted because it parked rejoins automatically
    once its snooze or follow-up date passes.
    """
    now = now or utcnow()
    tasks = session.exec(select(Task).order_by(col(Task.created_at).desc())).all()
    by_id = {task.id: task for task in tasks}
    inflight = [task for task in tasks if task.status in IN_FLIGHT_STATUSES]

    entries = active_entries(session)
    kept: list[StackEntry] = []
    dropped: list[tuple[StackEntry, str | None]] = []
    for entry in entries:
        task = by_id.get(entry.task_id)
        if task is None or task.status not in IN_FLIGHT_STATUSES:
            dropped.append((entry, None))
        elif is_parked(task, now):
            dropped.append((entry, "parked"))
        else:
            kept.append(entry)

    # The most recent entry per task (active or not) decides whether the task
    # may join: no entry yet, or its last entry left because it parked.
    latest: dict[str, StackEntry] = {}
    for entry in session.exec(select(StackEntry).order_by(col(StackEntry.created_at))).all():
        latest[entry.task_id] = entry

    on_stack = {entry.task_id for entry in kept}
    added: list[StackEntry] = []
    for task in inflight:
        if task.id in on_stack or is_parked(task, now):
            continue
        previous = latest.get(task.id)
        if previous is None:
            added.append(StackEntry(task_id=task.id))
        elif previous.deleted_reason == "parked":
            # Restore the parked entry so its sessions and execution count
            # survive the deferral instead of starting a fresh one.
            previous.deleted_at = None
            previous.deleted_reason = None
            previous.is_current = False
            session.add(previous)
            added.append(previous)

    if not dropped and not added:
        return entries

    for entry, reason in dropped:
        _soft_delete(session, entry, now, reason)
    for entry in added:
        session.add(entry)
    ordered = kept + added
    _reindex(session, ordered)
    _set_current(session, ordered, now)
    session.commit()
    return active_entries(session)


def push(
    session: Session,
    *,
    title: str = "",
    description: str = "",
    position: str = "top",
    task: Task | None = None,
    now: datetime | None = None,
) -> list[StackEntry]:
    """Add a task to the stack. ``position`` is top, next (after current), or last."""
    now = now or utcnow()
    entries = active_entries(session)
    if task is None:
        task = Task(title=title.strip(), description=description.strip())
        session.add(task)
        session.commit()
        session.refresh(task)

    # Pushing a parked task is an explicit "work on it now", so drop its snooze
    # and waiting state; otherwise the next sync would park it again. A blocked
    # task being worked on again reopens.
    if task.snoozed_until is not None or task.waiting_on_person_id is not None:
        was_waiting = task.waiting_on_person_id is not None
        task.snoozed_until = None
        task.waiting_on_person_id = None
        task.follow_up_at = None
        if was_waiting and task.status == TaskStatus.blocked:
            task.status = TaskStatus.open
        task.updated_at = now
        session.add(task)

    # Reuse the entry a parking left behind, so pushing it back keeps its
    # sessions and execution count.
    entry = session.exec(
        select(StackEntry)
        .where(StackEntry.task_id == task.id)
        .where(StackEntry.deleted_reason == "parked")
        .order_by(col(StackEntry.created_at).desc())
    ).first()
    if entry is not None:
        entry.deleted_at = None
        entry.deleted_reason = None
        entry.is_current = False
        session.add(entry)
    else:
        entry = StackEntry(task_id=task.id)
        session.add(entry)
    session.flush()
    if position == "next" and entries:
        entries.insert(1, entry)
    elif position == "last":
        entries.append(entry)
    else:
        entries.insert(0, entry)

    _reindex(session, entries)
    _set_current(session, entries, now)
    session.commit()
    add_timeline(session, task.id, "stack_pushed", "Added to the stack")
    return active_entries(session)


def pop(session: Session, now: datetime | None = None) -> list[StackEntry]:
    """Pop the current task: mark it done, soft-delete it, and promote the next."""
    now = now or utcnow()
    entries = active_entries(session)
    if not entries:
        return []
    removed = entries.pop(0)
    _soft_delete(session, removed, now, "popped")
    task = session.get(Task, removed.task_id)
    if task is not None:
        task.status = TaskStatus.done
        task.updated_at = now
        session.add(task)
    _reindex(session, entries)
    _set_current(session, entries, now)
    session.commit()
    if task is not None:
        add_timeline(session, task.id, "stack_popped", "Completed and popped from the stack")
    return active_entries(session)


def remove(session: Session, entry_id: str, now: datetime | None = None) -> list[StackEntry]:
    """Soft-delete an entry from anywhere in the stack (no status change)."""
    now = now or utcnow()
    entries = active_entries(session)
    target = next((entry for entry in entries if entry.id == entry_id), None)
    if target is None:
        return entries
    entries.remove(target)
    _soft_delete(session, target, now, "removed")
    _reindex(session, entries)
    _set_current(session, entries, now)
    session.commit()
    add_timeline(session, target.task_id, "stack_removed", "Removed from the stack")
    return active_entries(session)


def reorder(session: Session, entry_id: str, target_position: int, now: datetime | None = None) -> list[StackEntry]:
    """Move an entry to ``target_position``, keeping the rest in order."""
    now = now or utcnow()
    entries = active_entries(session)
    index = next((i for i, entry in enumerate(entries) if entry.id == entry_id), None)
    if index is None:
        return entries
    target = max(0, min(len(entries) - 1, target_position))
    if target == index:
        return entries
    entry = entries.pop(index)
    entries.insert(target, entry)
    _reindex(session, entries)
    _set_current(session, entries, now)
    session.commit()
    return active_entries(session)


def promote(session: Session, entry_id: str, now: datetime | None = None) -> list[StackEntry]:
    """Move an entry to the top of the stack (position 0), making it current."""
    return reorder(session, entry_id, 0, now)


def update_entry(
    session: Session,
    entry_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
) -> list[StackEntry]:
    """Edit the task behind a stack entry (its title and/or description)."""
    entries = active_entries(session)
    entry = next((item for item in entries if item.id == entry_id), None)
    if entry is None:
        return entries
    task = session.get(Task, entry.task_id)
    if task is not None:
        if title is not None and title.strip():
            task.title = title.strip()
        if description is not None:
            task.description = description
        task.updated_at = utcnow()
        session.add(task)
        session.commit()
    return active_entries(session)


def current_entry(session: Session) -> StackEntry | None:
    entries = active_entries(session)
    return entries[0] if entries else None


__all__ = [
    "EntryStats",
    "IN_FLIGHT_STATUSES",
    "active_entries",
    "current_entry",
    "entry_stats",
    "history_entries",
    "is_parked",
    "parked_reason",
    "pop",
    "promote",
    "push",
    "remove",
    "reorder",
    "sessions_for",
    "sync_stack",
    "update_entry",
]
