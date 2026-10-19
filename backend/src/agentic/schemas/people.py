"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .base import ORMModel


class PersonCreate(BaseModel):
    name: str = ""
    aliases: list[str] = []
    notes: str = ""


class PersonUpdate(BaseModel):
    name: str | None = None
    aliases: list[str] | None = None
    notes: str | None = None


class PersonRead(ORMModel):
    id: str
    name: str
    aliases: list[str] = []
    notes: str
    created_at: datetime
    updated_at: datetime
    task_count: int = 0
    item_count: int = 0


class PersonDetail(PersonRead):
    """A person with the tasks and items they are attached to.

    ``task_ids`` is every task the person is attached to; ``involved_task_ids``
    and ``requester_task_ids`` split that set by how they are attached (as a
    person on the task, as the requester, or both).
    """

    task_ids: list[str] = []
    involved_task_ids: list[str] = []
    requester_task_ids: list[str] = []
    item_ids: list[str] = []


class PersonLink(BaseModel):
    """Link an existing person (``person_id``) or create and link a new one (``name``)."""

    person_id: str | None = None
    name: str = ""


class PersonMerge(BaseModel):
    """Merge ``source_id`` into the person in the path, which survives."""

    source_id: str


class SlackAliasNames(BaseModel):
    """Slack user ids carried as aliases, mapped to the display name slackx knows."""

    names: dict[str, str] = {}


class TagRead(BaseModel):
    """A tag in use, with how many tasks carry it."""

    name: str
    count: int
