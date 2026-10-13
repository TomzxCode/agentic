"""Operations: the audit log of mutating requests.

The middleware in ``provenance`` writes one row per mutating ``/api`` request,
so this router only reads them back. It is the cross-cutting view of how work
entered the system, covering operations that have no task to hang a timeline
event off (settings, repositories, harnesses, people).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, col, select

from ..db import get_session
from ..models import Operation
from ..schemas import OperationRead

router = APIRouter(prefix="/api/operations", tags=["operations"])


@router.get("", response_model=list[OperationRead])
def list_operations(
    client: str | None = None,
    actor: str | None = None,
    limit: int = 100,
    session: Session = Depends(get_session),
) -> list[Operation]:
    query = select(Operation).order_by(col(Operation.created_at).desc()).limit(max(1, min(limit, 500)))
    if client:
        query = query.where(Operation.client == client)
    if actor:
        query = query.where(Operation.actor == actor)
    return list(session.exec(query).all())


__all__ = ["router"]
