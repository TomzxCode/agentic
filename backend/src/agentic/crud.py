"""Small shared CRUD helpers for routers."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from enum import Enum
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from . import provenance
from .models.base import OperationActor, OperationClient
from .models.tasks import Task, TimelineEvent


def jsonable(value: Any) -> Any:
    """Make a value safe for the JSON timeline column (enums and datetimes -> strings)."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    return value


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


def get_or_404[ModelT](session: Session, model: type[ModelT], row_id: str, detail: str) -> ModelT:
    """Fetch a row by primary key or raise the 404 the caller's route expects.

    ``detail`` is passed whole (e.g. ``"Person not found"``) so each router keeps
    its own wording.
    """
    row = session.get(model, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail=detail)
    return row


def get_task_or_404(session: Session, task_id: str) -> Task:
    return get_or_404(session, Task, task_id, "Task not found")


def add_timeline(
    session: Session,
    task_id: str,
    type_: str,
    message: str = "",
    data: dict[str, Any] | None = None,
    *,
    client: OperationClient | None = None,
    actor: OperationActor | None = None,
) -> TimelineEvent:
    event = TimelineEvent(
        task_id=task_id,
        type=type_,
        message=message,
        data_json=data or {},
        client=client or provenance.current_client(),
        actor=actor or provenance.current_actor(),
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event
