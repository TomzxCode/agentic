"""Small shared CRUD helpers for routers."""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from .models import Task, TimelineEvent


def jsonable(value: Any) -> Any:
    """Make a value safe for the JSON timeline column (enums -> their value)."""
    return value.value if isinstance(value, Enum) else value


def normalize_tags(tags: Iterable[str]) -> list[str]:
    """Trim, drop empties, and de-duplicate a tag list, preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in tags:
        name = str(raw).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


# Human-readable names for fields that hold a foreign key.
FIELD_LABELS = {"group_id": "group", "harness_id": "harness"}


def field_label(key: str) -> str:
    return FIELD_LABELS.get(key, key.replace("_", " "))


def get_task_or_404(session: Session, task_id: str) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def add_timeline(
    session: Session,
    task_id: str,
    type_: str,
    message: str = "",
    data: dict[str, Any] | None = None,
) -> TimelineEvent:
    event = TimelineEvent(task_id=task_id, type=type_, message=message, data_json=data or {})
    session.add(event)
    session.commit()
    session.refresh(event)
    return event
