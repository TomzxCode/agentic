"""Small shared CRUD helpers for routers."""

from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from .models import Problem, TimelineEvent


def jsonable(value: Any) -> Any:
    """Make a value safe for the JSON timeline column (enums -> their value)."""
    return value.value if isinstance(value, Enum) else value


def get_problem_or_404(session: Session, problem_id: str) -> Problem:
    problem = session.get(Problem, problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    return problem


def add_timeline(
    session: Session,
    problem_id: str,
    type_: str,
    message: str = "",
    data: dict[str, Any] | None = None,
) -> TimelineEvent:
    event = TimelineEvent(problem_id=problem_id, type=type_, message=message, data_json=data or {})
    session.add(event)
    session.commit()
    session.refresh(event)
    return event
