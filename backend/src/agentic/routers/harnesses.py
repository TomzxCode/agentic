"""Harnesses: the ACP agent command configurations.

Mounted under ``/api``; the run and stream endpoints live in ``agent_runs.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import delete as sa_delete
from sqlalchemy import update as sa_update
from sqlmodel import Session, col, select

from ..agents.harnesses import harness_available, resolve_default_model, seed_harnesses
from ..agents.pool import pool
from ..crud import get_or_404
from ..db import get_session
from ..models.agents import AgentRun, AgentSession, Harness
from ..models.tasks import Task
from ..schemas.harnesses import (
    HarnessCreate,
    HarnessModelsRead,
    HarnessRead,
    HarnessStatus,
    HarnessUpdate,
)

router = APIRouter(prefix="/api", tags=["agents"])


def _harness_read(harness: Harness) -> HarnessRead:
    """A harness with its config file's default model resolved for display."""
    read = HarnessRead.model_validate(harness)
    read.default_model = resolve_default_model(harness)
    return read


@router.get("/harnesses", response_model=list[HarnessStatus])
def list_harnesses(session: Session = Depends(get_session)) -> list[HarnessStatus]:
    seed_harnesses(session)
    statuses: list[HarnessStatus] = []
    for harness in session.exec(select(Harness)).all():
        available, detail = harness_available(harness)
        statuses.append(
            HarnessStatus(
                id=harness.id,
                name=harness.name,
                available=available,
                detail=detail,
                is_default=harness.is_default,
                model=harness.model,
                default_model=resolve_default_model(harness),
            )
        )
    return statuses


@router.get("/harnesses/full", response_model=list[HarnessRead])
def list_harnesses_full(session: Session = Depends(get_session)) -> list[HarnessRead]:
    seed_harnesses(session)
    return [_harness_read(harness) for harness in session.exec(select(Harness)).all()]


@router.get("/harnesses/{harness_id}/models", response_model=HarnessModelsRead)
async def list_harness_models(harness_id: str, session: Session = Depends(get_session)) -> HarnessModelsRead:
    """The models a harness offers, for the task view's model picker.

    Answered from the session the API holds open for this harness (the default
    harness's is up from startup, any other's from its first ask), so repeated
    asks reuse one session instead of spawning a harness each time. A harness
    that cannot be asked returns an empty list and the reason in ``error``.
    """
    harness = get_or_404(session, Harness, harness_id, "Harness not found")
    models = await pool.models(harness)
    return HarnessModelsRead(
        harness_id=models.harness_id,
        models=models.choices,
        current=models.current,
        live=models.live,
        error=models.error,
    )


@router.post("/harnesses", response_model=HarnessRead, status_code=201)
def create_harness(payload: HarnessCreate, session: Session = Depends(get_session)) -> HarnessRead:
    harness = Harness(**payload.model_dump())
    if harness.is_default:
        session.exec(sa_update(Harness).where(col(Harness.id) != harness.id).values(is_default=False))
    session.add(harness)
    session.commit()
    session.refresh(harness)
    pool.refresh()
    return _harness_read(harness)


@router.patch("/harnesses/{harness_id}", response_model=HarnessRead)
def update_harness(harness_id: str, payload: HarnessUpdate, session: Session = Depends(get_session)) -> HarnessRead:
    harness = get_or_404(session, Harness, harness_id, "Harness not found")
    data = payload.model_dump(exclude_unset=True)
    # At most one default: promoting a harness demotes the others.
    if data.get("is_default"):
        session.exec(sa_update(Harness).where(col(Harness.id) != harness_id).values(is_default=False))
    for key, value in data.items():
        setattr(harness, key, value)
    session.add(harness)
    session.commit()
    session.refresh(harness)
    pool.refresh()
    return _harness_read(harness)


@router.delete("/harnesses/{harness_id}", status_code=204)
def delete_harness(harness_id: str, session: Session = Depends(get_session)) -> None:
    harness = get_or_404(session, Harness, harness_id, "Harness not found")
    session.exec(sa_update(Task).where(col(Task.harness_id) == harness.id).values(harness_id=None))
    session.exec(sa_update(AgentRun).where(col(AgentRun.harness_id) == harness.id).values(harness_id=None))
    session.exec(sa_update(AgentSession).where(col(AgentSession.harness_id) == harness.id).values(harness_id=None))
    session.exec(sa_delete(Harness).where(col(Harness.id) == harness.id))
    session.commit()
    pool.refresh()


__all__ = ["router"]
