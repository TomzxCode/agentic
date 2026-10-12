"""Tags: the labels carried by tasks, with their task counts.

Tags live as a JSON list on each task rather than in their own table, so this
router derives the set of tags in use from the tasks themselves. It is the
enumeration a future view needs to offer tag filters.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..db import get_session
from ..models import Task
from ..schemas import TagRead

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=list[TagRead])
def list_tags(session: Session = Depends(get_session)) -> list[TagRead]:
    """List the tags in use, most used first, then alphabetically."""
    counts: dict[str, int] = {}
    for task in session.exec(select(Task)).all():
        for name in task.tags or []:
            counts[name] = counts.get(name, 0) + 1
    return [
        TagRead(name=name, count=count)
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
    ]


__all__ = ["router"]
