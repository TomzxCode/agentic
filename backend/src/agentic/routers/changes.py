"""Changes: the unit of factory output the metrics are computed from.

A change is an explicit, task-scoped record with an id, a start, an end, and a
human-intervened flag. Recording the lifecycle and the interventions here is
what lets the metrics engine compute autonomy rate and yield honestly; nothing
else works until this exists.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete
from sqlmodel import Session, col, select

from ..crud import add_timeline, get_task_or_404, jsonable
from ..db import get_session
from ..events import bus
from ..models import (
    Change,
    ChangeClass,
    ChangeIntervention,
    ChangeStatus,
    InterventionKind,
    Repository,
    Worktree,
    utcnow,
)
from ..schemas import (
    ChangeCreate,
    ChangeDetail,
    ChangeRead,
    ChangeStatusUpdate,
    ChangeUpdate,
    InterventionCreate,
    InterventionRead,
)

router = APIRouter(prefix="/api/changes", tags=["changes"])

# The lifecycle graph. Setting the current status again is a no-op; anything
# else not listed here is rejected, so a change's history stays coherent.
ALLOWED_TRANSITIONS: dict[ChangeStatus, set[ChangeStatus]] = {
    ChangeStatus.proposed: {ChangeStatus.verified, ChangeStatus.accepted, ChangeStatus.rejected},
    ChangeStatus.verified: {ChangeStatus.accepted, ChangeStatus.rejected},
    ChangeStatus.accepted: {ChangeStatus.reverted},
    ChangeStatus.rejected: set(),
    ChangeStatus.reverted: set(),
}


def _enum_or_400[E: StrEnum](enum: type[E], value: str, label: str) -> E:
    try:
        return enum(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in cast(Iterable[E], enum))
        raise HTTPException(status_code=400, detail=f"Unknown {label}: {value} (allowed: {allowed})") from exc


def _get_change_or_404(session: Session, change_id: str) -> Change:
    change = session.get(Change, change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Change not found")
    return change


def _detail(session: Session, change: Change) -> ChangeDetail:
    interventions = session.exec(
        select(ChangeIntervention)
        .where(ChangeIntervention.change_id == change.id)
        .order_by(col(ChangeIntervention.created_at).desc())
    ).all()
    return ChangeDetail(
        **ChangeRead.model_validate(change).model_dump(),
        interventions=[InterventionRead.model_validate(i) for i in interventions],
    )


async def _announce(task_id: str) -> None:
    """Tell any task-page subscriber that its changes list moved."""
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "changes_changed"})


@router.get("", response_model=list[ChangeRead])
def list_changes(
    task_id: str | None = None,
    status: str | None = None,
    change_class: str | None = None,
    session: Session = Depends(get_session),
) -> list[Change]:
    query = select(Change).order_by(col(Change.opened_at).desc())
    if task_id:
        query = query.where(Change.task_id == task_id)
    if status:
        query = query.where(Change.status == _enum_or_400(ChangeStatus, status, "status"))
    if change_class:
        query = query.where(Change.change_class == _enum_or_400(ChangeClass, change_class, "class"))
    return list(session.exec(query).all())


@router.post("", response_model=ChangeRead, status_code=201)
async def create_change(payload: ChangeCreate, session: Session = Depends(get_session)) -> Change:
    get_task_or_404(session, payload.task_id)
    data = payload.model_dump(exclude={"change_class", "opened_at", "status", "accepted_at"})
    data["change_class"] = _enum_or_400(ChangeClass, payload.change_class, "class")
    status = _enum_or_400(ChangeStatus, payload.status, "status")
    if status not in (ChangeStatus.proposed, ChangeStatus.verified, ChangeStatus.accepted):
        raise HTTPException(status_code=400, detail=f"A change cannot be created as {status}")
    data["status"] = status
    if payload.opened_at is not None:
        data["opened_at"] = payload.opened_at
    if status == ChangeStatus.verified:
        data["verified_at"] = utcnow()
    elif status == ChangeStatus.accepted:
        # A change that opens accepted (an imported merged PR) dates its end to
        # the merge, not to the moment it was recorded.
        data["accepted_at"] = payload.accepted_at or payload.opened_at or utcnow()
    if payload.repository_id and session.get(Repository, payload.repository_id) is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    if payload.worktree_id and session.get(Worktree, payload.worktree_id) is None:
        raise HTTPException(status_code=404, detail="Worktree not found")
    change = Change(**data)
    session.add(change)
    session.commit()
    session.refresh(change)
    add_timeline(
        session,
        change.task_id,
        "change_opened",
        f"Change opened: {change.title or change.id}",
        {"change_id": change.id, "change_class": jsonable(change.change_class)},
    )
    await _announce(change.task_id)
    return change


@router.get("/{change_id}", response_model=ChangeDetail)
def get_change(change_id: str, session: Session = Depends(get_session)) -> ChangeDetail:
    return _detail(session, _get_change_or_404(session, change_id))


@router.patch("/{change_id}", response_model=ChangeRead)
async def update_change(change_id: str, payload: ChangeUpdate, session: Session = Depends(get_session)) -> Change:
    change = _get_change_or_404(session, change_id)
    data = payload.model_dump(exclude_unset=True)
    if "change_class" in data and data["change_class"] is not None:
        data["change_class"] = _enum_or_400(ChangeClass, data["change_class"], "class")
    for key, value in data.items():
        setattr(change, key, value)
    change.updated_at = utcnow()
    session.add(change)
    session.commit()
    session.refresh(change)
    await _announce(change.task_id)
    return change


@router.post("/{change_id}/status", response_model=ChangeRead)
async def transition_change(
    change_id: str, payload: ChangeStatusUpdate, session: Session = Depends(get_session)
) -> Change:
    change = _get_change_or_404(session, change_id)
    target = _enum_or_400(ChangeStatus, payload.status, "status")
    if target == change.status:
        return change
    if target not in ALLOWED_TRANSITIONS[change.status]:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot move a change from {change.status} to {target}",
        )
    change.status = target
    if target == ChangeStatus.verified:
        change.verified_at = utcnow()
    elif target == ChangeStatus.accepted:
        change.accepted_at = utcnow()
    elif target in (ChangeStatus.rejected, ChangeStatus.reverted):
        change.closed_at = utcnow()
    change.updated_at = utcnow()
    session.add(change)
    session.commit()
    session.refresh(change)
    add_timeline(
        session,
        change.task_id,
        f"change_{target}",
        f"Change {target}: {change.title or change.id}",
        {"change_id": change.id, "status": jsonable(target)},
    )
    await _announce(change.task_id)
    return change


@router.post("/{change_id}/interventions", response_model=InterventionRead, status_code=201)
async def add_intervention(
    change_id: str, payload: InterventionCreate, session: Session = Depends(get_session)
) -> ChangeIntervention:
    change = _get_change_or_404(session, change_id)
    kind = _enum_or_400(InterventionKind, payload.kind, "intervention kind")
    intervention = ChangeIntervention(change_id=change.id, kind=kind, note=payload.note)
    session.add(intervention)
    change.human_intervened = True
    change.intervention_count += 1
    change.updated_at = utcnow()
    session.add(change)
    session.commit()
    session.refresh(intervention)
    add_timeline(
        session,
        change.task_id,
        "change_intervened",
        f"Human intervention ({kind}): {change.title or change.id}",
        {"change_id": change.id, "kind": jsonable(kind)},
    )
    await _announce(change.task_id)
    return intervention


@router.delete("/{change_id}", status_code=204)
async def delete_change(change_id: str, session: Session = Depends(get_session)) -> None:
    change = _get_change_or_404(session, change_id)
    task_id = change.task_id
    session.exec(sa_delete(ChangeIntervention).where(col(ChangeIntervention.change_id) == change.id))
    session.exec(sa_delete(Change).where(col(Change.id) == change.id))
    session.commit()
    await _announce(task_id)


__all__ = ["router", "ALLOWED_TRANSITIONS", "_detail"]
