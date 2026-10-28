"""Ask a pull request reviewer for a review over Slack.

Both the item view (which has the stored item) and the standalone pull request
view (which only knows the URL) send the same message from the same people
lookup, so the work lives here rather than in either router.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlmodel import Session

from ..schemas.items import ItemPoke
from ..services.github import pr_review_request_message
from ..services.slack import SlackError, resolve_slack_user_id, slack_send_dm
from .people_service import person_aliases, person_for_alias


def poke_pull_request_reviewer(session: Session, url: str, title: str, login: str) -> ItemPoke:
    """Send one reviewer the PR review request, resolving their Slack user.

    The GitHub login resolves through the people directory: the person carrying
    it as an alias supplies the Slack user id (or handle) the message goes to.
    The DM is sent with Slack's ``chat.postMessage``, which opens it if needed.
    """
    login = (login or "").strip()
    if not login:
        raise HTTPException(status_code=400, detail="Provide the reviewer's GitHub login")
    person = person_for_alias(session, login)
    if person is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No person carries the GitHub login @{login}. Create them in People with that login "
                "and their Slack user id as aliases, then poke again."
            ),
        )
    slack_user_id = resolve_slack_user_id(person_aliases(session, person.id))
    if slack_user_id is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{person.name} has no Slack user id or handle among their aliases. "
                "Add one on their person page, then poke again."
            ),
        )
    try:
        # The PR link is the whole message, so no preview: the DM stays one line.
        sent = slack_send_dm(slack_user_id, pr_review_request_message(url, title), unfurl=False)
    except SlackError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ItemPoke(
        login=login,
        slack_user_id=slack_user_id,
        name=person.name,
        ts=str(sent["ts"]) if sent.get("ts") else None,
    )
