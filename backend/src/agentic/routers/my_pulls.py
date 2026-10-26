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

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlmodel import Session, col, select

from ..db import get_session
from ..models.base import utcnow
from ..models.items import Association, SourceItem
from ..models.tasks import Task
from ..my_pulls import fetch_my_pull_checks, fetch_my_pulls
from ..schemas.my_pulls import (
    MyPullChecksRead,
    MyPullPokeFailure,
    MyPullPokeRead,
    MyPullPokeRequest,
    MyPullPokeSent,
    MyPullsRead,
    MyPullTask,
)
from ..services.github import pr_review_request_message
from ..services.slack import SlackError, resolve_slack_user_id, slack_send_dm
from ..settings_store import resolve_github_login
from .people_service import person_aliases, person_for_alias

router = APIRouter(prefix="/api/my-pulls", tags=["my-pulls"])

#: A repository as ``owner/name``; anything else is a bad coordinate, not a read.
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _tasks_by_pull(session: Session, pulls: list[dict]) -> dict[str, list[MyPullTask]]:
    """The tasks each pull request is linked to, keyed by its external id.

    A pull request's stored item carries ``owner/repo#number`` as its external
    id, so the row joins back to its tasks through that. The key is lowercased
    because GitHub's casing of a repository can differ from the casing the item
    was created with.
    """
    keys = {f"{pull['repository']}#{pull['number']}".lower() for pull in pulls if pull.get("repository")}
    if not keys:
        return {}
    item_ids_by_key: dict[str, list[str]] = {}
    for item in session.exec(
        select(SourceItem).where(
            SourceItem.source == "github",
            func.lower(col(SourceItem.external_id)).in_(keys),
        )
    ).all():
        if item.external_id:
            item_ids_by_key.setdefault(item.external_id.lower(), []).append(item.id)
    item_ids = [item_id for ids in item_ids_by_key.values() for item_id in ids]
    if not item_ids:
        return {}
    task_ids_by_item: dict[str, list[str]] = {}
    for assoc in session.exec(select(Association).where(col(Association.item_id).in_(item_ids))).all():
        task_ids_by_item.setdefault(assoc.item_id, []).append(assoc.task_id)
    task_ids = {task_id for ids in task_ids_by_item.values() for task_id in ids}
    if not task_ids:
        return {}
    tasks = {
        task.id: MyPullTask(id=task.id, title=task.title, status=task.status)
        for task in session.exec(select(Task).where(col(Task.id).in_(task_ids))).all()
    }
    linked: dict[str, list[MyPullTask]] = {}
    for key, ids in item_ids_by_key.items():
        rows = {
            task_id: tasks[task_id]
            for item_id in ids
            for task_id in task_ids_by_item.get(item_id, [])
            if task_id in tasks
        }
        if rows:
            linked[key] = list(rows.values())
    return linked


@router.get("", response_model=MyPullsRead)
def list_my_pulls(refresh: bool = False, session: Session = Depends(get_session)) -> MyPullsRead:
    """The open pull requests authored by the configured GitHub login.

    ``refresh`` re-queries GitHub instead of reusing the short cache, the way
    the review queue's Refresh works. With no login configured, or with a `gh`
    that could not run, the response carries an ``error`` and no pull requests.
    """
    report = fetch_my_pulls(resolve_github_login(session), refresh=refresh)
    # The cached GitHub read carries no task links, so copy each row and add
    # them here: linking or unlinking a task shows at once, without a re-query.
    tasks = _tasks_by_pull(session, report["pulls"])
    pulls = [
        {**pull, "tasks": tasks.get(f"{pull['repository']}#{pull['number']}".lower(), [])} for pull in report["pulls"]
    ]
    return MyPullsRead(
        login=str(report.get("login") or ""),
        generated_at=utcnow(),
        counts=report.get("counts") or {},
        error=report.get("error"),
        pulls=pulls,
    )


@router.get("/checks", response_model=MyPullChecksRead)
def list_my_pull_checks(repository: str, number: int, refresh: bool = False) -> MyPullChecksRead:
    """The individual checks behind one pull request's CI badge, read live.

    The page load carries only the rollup state, so this read runs when the
    badge's popover opens. A read that could not run carries an ``error`` and no
    checks, so the popover can say what is wrong instead of reading as a pull
    request with nothing to run. ``refresh`` asks GitHub again instead of
    reusing the short cache, which is what the popover's retry does.
    """
    if not _REPOSITORY_RE.match(repository) or number < 1:
        raise HTTPException(
            status_code=400,
            detail="Provide a repository as owner/name and a positive pull request number",
        )
    owner, _, repo = repository.partition("/")
    report = fetch_my_pull_checks(owner, repo, number, refresh=refresh)
    return MyPullChecksRead(repository=repository, number=number, **report)


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
