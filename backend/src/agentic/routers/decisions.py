"""The colleague-decisions page: decisions read from the notes tree.

``extract-colleague-decisions`` writes one report per day under the notes root
(``decisions/YYYY/MM/DD.md``), naming each colleague's decisions and who
supported or opposed them. This router reads those reports into one payload the
SPA's Decisions page renders. It is read-only: the reports belong to the skill.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..config import settings
from ..decisions_store import build_payload, discover_reports
from ..models.base import utcnow
from ..schemas.decisions import DecisionRead, DecisionsRead

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


@router.get("", response_model=DecisionsRead)
def list_decisions() -> DecisionsRead:
    """Every decision report under the configured notes root, aggregated.

    A notes root that does not exist (or is not configured) yields an empty
    payload with ``root`` null, so the page can explain what to set instead of
    failing.
    """
    root = settings.notes_dir.expanduser()
    reports = discover_reports(root) if root.is_dir() else []
    payload = build_payload(reports)
    return DecisionsRead(
        root=str(root) if root.is_dir() else None,
        generated_at=utcnow(),
        reports=payload["reports"],
        counts=payload["counts"],
        range=payload["range"],
        decisions=[DecisionRead.model_validate(decision, from_attributes=True) for decision in payload["decisions"]],
        headlines=payload["headlines"],
        not_heard=payload["not_heard"],
        cross_cutting=payload["cross_cutting"],
    )


__all__ = ["router"]
