"""My PRs: the open pull requests the viewer authored, with their state.

One read answers the whole page (the open threads, the check rollup, the review
decision and approvers) from a single GraphQL search, cached briefly; this
router only resolves who "my" is and wraps the result in the response model.
Nothing is stored, so a pull request that merges leaves the page on the next
refresh without a bookkeeping step.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..db import get_session
from ..models.base import utcnow
from ..my_pulls import fetch_my_pulls
from ..schemas.my_pulls import MyPullsRead
from ..settings_store import resolve_github_login

router = APIRouter(prefix="/api/my-pulls", tags=["my-pulls"])


@router.get("", response_model=MyPullsRead)
def list_my_pulls(refresh: bool = False, session: Session = Depends(get_session)) -> MyPullsRead:
    """The open pull requests authored by the configured GitHub login.

    ``refresh`` re-queries GitHub instead of reusing the short cache, the way
    the review queue's Refresh works. With no login configured, or with a `gh`
    that could not run, the response carries an ``error`` and no pull requests.
    """
    report = fetch_my_pulls(resolve_github_login(session), refresh=refresh)
    return MyPullsRead(generated_at=utcnow(), **report)


__all__ = ["router"]
