"""The counts the sidebar nav badges show."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..db import get_session
from ..nav_badges import feedback_count, my_pulls_count, review_count
from ..schemas.badges import NavBadgesRead

router = APIRouter(prefix="/api/badges", tags=["badges"])


@router.get("", response_model=NavBadgesRead)
def read_badges(session: Session = Depends(get_session)) -> NavBadgesRead:
    """How much awaits the viewer on the Review queue, My PRs, and PR feedback.

    The counts come from the same stores the pages read, without forcing a live
    GitHub refresh, so the shell can ask once per load.
    """
    return NavBadgesRead(
        reviews=review_count(session),
        my_pulls=my_pulls_count(session),
        feedback=feedback_count(),
    )


__all__ = ["router"]
