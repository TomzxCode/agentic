"""Agent sessions recorded against a task.

A run already carries the session it produced; this resource records a session
attached by hand (for example one started in OpenChamber), so a task shows every
session it was worked in and the ways to reopen them.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from ..crud import add_timeline, get_task_or_404
from ..db import get_session
from ..events import bus
from ..links import session_read
from ..models import AgentSession, Harness, Task
from ..schemas import SessionCreate, SessionRead, SessionUpdate

router = APIRouter(prefix="/api/tasks", tags=["sessions"])


def _resolve_harness_id(session: Session, task: Task, harness_id: str | None) -> str | None:
    """Pick the harness a session runs on: the explicit one, else the task's."""
    if not harness_id:
        return task.harness_id
    if session.get(Harness, harness_id) is None:
        raise HTTPException(status_code=404, detail="Harness not found")
    return harness_id


def _get_or_404(session: Session, task_id: str, session_id: str) -> AgentSession:
    row = session.get(AgentSession, session_id)
    if row is None or row.task_id != task_id:
        raise HTTPException(status_code=404, detail="Session not found")
    return row


@router.get("/{task_id}/sessions", response_model=list[SessionRead])
def list_sessions(task_id: str, session: Session = Depends(get_session)) -> list[SessionRead]:
    get_task_or_404(session, task_id)
    rows = session.exec(
        select(AgentSession).where(AgentSession.task_id == task_id).order_by(col(AgentSession.created_at).desc())
    ).all()
    return [session_read(session, row) for row in rows]


@router.post("/{task_id}/sessions", response_model=SessionRead, status_code=201)
async def create_session(task_id: str, payload: SessionCreate, session: Session = Depends(get_session)) -> SessionRead:
    task = get_task_or_404(session, task_id)
    if not payload.session_id.strip():
        raise HTTPException(status_code=400, detail="A session id is required")
    row = AgentSession(
        task_id=task_id,
        harness_id=_resolve_harness_id(session, task, payload.harness_id),
        session_id=payload.session_id.strip(),
        label=payload.label,
        cwd=str(Path(payload.cwd).expanduser()) if payload.cwd else None,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    add_timeline(
        session,
        task_id,
        "session_added",
        f"Agent session {row.session_id} attached",
        {"id": row.id, "session_id": row.session_id},
    )
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "sessions_changed"})
    return session_read(session, row)


@router.get("/{task_id}/sessions/{session_id}", response_model=SessionRead)
def read_session(task_id: str, session_id: str, session: Session = Depends(get_session)) -> SessionRead:
    get_task_or_404(session, task_id)
    return session_read(session, _get_or_404(session, task_id, session_id))


@router.patch("/{task_id}/sessions/{session_id}", response_model=SessionRead)
async def update_session(
    task_id: str, session_id: str, payload: SessionUpdate, session: Session = Depends(get_session)
) -> SessionRead:
    row = _get_or_404(session, task_id, session_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("harness_id") and session.get(Harness, data["harness_id"]) is None:
        raise HTTPException(status_code=404, detail="Harness not found")
    if data.get("cwd"):
        data["cwd"] = str(Path(data["cwd"]).expanduser())
    for key, value in data.items():
        setattr(row, key, value)
    session.add(row)
    session.commit()
    session.refresh(row)
    add_timeline(
        session,
        task_id,
        "session_updated",
        f"Agent session {row.session_id} updated",
        {"id": row.id, "session_id": row.session_id},
    )
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "sessions_changed"})
    return session_read(session, row)


@router.delete("/{task_id}/sessions/{session_id}", status_code=204)
async def delete_session(task_id: str, session_id: str, session: Session = Depends(get_session)) -> None:
    row = _get_or_404(session, task_id, session_id)
    agent_session_id = row.session_id
    session.delete(row)
    session.commit()
    add_timeline(
        session,
        task_id,
        "session_removed",
        f"Agent session {agent_session_id} removed",
        {"id": session_id, "session_id": agent_session_id},
    )
    await bus.publish(f"task:{task_id}", {"kind": "task", "action": "sessions_changed"})
