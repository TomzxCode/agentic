"""Slack: name the workspace users slackx caches, for the ids a caller passes.

A Slack-derived handle is a user id (``U0123ABCD``), which says nothing to a
reader. The people views resolve the aliases they are about to show through
here, so an id reads as a name without the stored value changing.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..schemas.slack import SlackUsers
from ..services.slack import resolve_slack_user_ids

router = APIRouter(prefix="/api/slack", tags=["slack"])


@router.get("/users", response_model=SlackUsers)
def list_users(ids: list[str] = Query(default=[])) -> SlackUsers:
    """Name the given Slack user ids through the slackx cache.

    The caller passes the values it is about to display, and only the ones that
    look like a Slack user id are read from slackx. Ids slackx cannot name are
    left out, and an empty result is not an error: slackx may be missing, or a
    value may be a handle rather than an id.
    """
    return SlackUsers(names=resolve_slack_user_ids(ids))
