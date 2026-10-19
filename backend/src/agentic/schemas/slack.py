"""Pydantic request/response models."""

from __future__ import annotations

from pydantic import BaseModel


class SlackUsers(BaseModel):
    """Slack user ids mapped to the display name slackx knows for them."""

    names: dict[str, str] = {}
