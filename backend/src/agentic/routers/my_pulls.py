"""My PRs: the open pull requests the viewer authored, with their state.

One read answers the whole page (the open threads, the check rollup, the review
decision and approvers) from a single GraphQL search, cached briefly; this
router only resolves who "my" is and wraps the result in the response model.
Nothing is stored, so a pull request that merges leaves the page on the next
refresh without a bookkeeping step.

The poke sends a pull request's requested reviewers a Slack DM asking for their
review, the same message the item page's poke sends. It names the pull request
by its fields rather than by a tracked item, because a pull request of yours
that GitHub still lists unreviewed is often not tracked as an item at all.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..models.base import utcnow
from ..my_pulls import fetch_my_pulls
from ..schemas.my_pulls import MyPullPokeFailure, MyPullPokeRead, MyPullPokeRequest, MyPullPokeSent, MyPullsRead
from ..services.github import pr_review_request_message
from ..services.slack import SlackError, resolve_slack_user_id, slack_send_dm
from ..settings_store import resolve_github_login
from .people_service import person_aliases, person_for_alias

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


@router.post("/poke", response_model=MyPullPokeRead)
def poke_my_pull_reviewers(payload: MyPullPokeRequest, session: Session = Depends(get_session)) -> MyPullPokeRead:
    """DM each named reviewer a Slack message asking for their review.

    The GitHub logins resolve through the people directory, the way the item
    page's poke does. Each reviewer is reported on its own: one person missing
    their Slack id does not stop the others from being reached. Logins are
    deduplicated, so requesting the same reviewer twice sends one message.
    """
    logins: list[str] = []
    for login in payload.logins:
        cleaned = login.strip()
        if cleaned and cleaned.lower() not in [sent.lower() for sent in logins]:
            logins.append(cleaned)
    if not logins:
        raise HTTPException(status_code=400, detail="Provide at least one reviewer's GitHub login")
    url = payload.url.strip() or f"https://github.com/{payload.repository}/pull/{payload.number}"
    message = pr_review_request_message(url, payload.title)

    poked: list[MyPullPokeSent] = []
    failed: list[MyPullPokeFailure] = []

    def unreachable(login: str, reason: str) -> None:
        failed.append(MyPullPokeFailure(login=login, reason=reason))

    for login in logins:
        person = person_for_alias(session, login)
        if person is None:
            unreachable(
                login,
                f"No person carries the GitHub login @{login}. Create them in People with that login, then poke again.",
            )
            continue
        slack_user_id = resolve_slack_user_id(person_aliases(session, person.id))
        if slack_user_id is None:
            unreachable(
                login,
                f"{person.name} has no Slack user id or handle among their aliases. "
                "Add one on their person page, then poke again.",
            )
            continue
        try:
            # The PR link is the whole message, so no preview: the DM stays one line.
            sent = slack_send_dm(slack_user_id, message, unfurl=False)
        except SlackError as exc:
            unreachable(login, str(exc))
            continue
        ts = str(sent["ts"]) if sent.get("ts") else None
        poked.append(MyPullPokeSent(login=login, name=person.name, slack_user_id=slack_user_id, ts=ts))
    return MyPullPokeRead(poked=poked, failed=failed)


__all__ = ["router"]
