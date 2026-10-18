"""SQLModel tables for items."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel

from .base import (
    new_id,
    utcnow,
)


class SourceItem(SQLModel, table=True):
    """Something external that can be associated to tasks."""

    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_external_id"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    source: str  # slack | github | gdrive | url | note | commit | file
    kind: str = ""  # thread | issue | pr | doc | ...
    title: str = ""
    # True once a person set the title; a refresh leaves a custom title alone
    # and only re-derives a title the source itself produced.
    title_custom: bool = False
    url: str | None = None
    external_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    content: str = ""  # pulled text (thread transcript, issue body, doc text)
    fetched_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Association(SQLModel, table=True):
    """Links a SourceItem to a Task (many-to-many) with provenance."""

    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    item_id: str = Field(foreign_key="sourceitem.id", index=True)
    note: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class Person(SQLModel, table=True):
    """An individual a task or a source item involves.

    People are a flat directory: a name plus a set of aliases. They link to
    tasks and items many-to-many through the ``taskperson`` and ``itemperson``
    join tables, so the same person can be seen from either side.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class PersonAlias(SQLModel, table=True):
    """An identifier for a person: a handle (GitHub login, Slack user id) or an email.

    A person carries many aliases in one flat list; the value is the identity
    used to de-duplicate people across sources, so a handle and an email are the
    same concept here (an identifier string).
    """

    __table_args__ = (UniqueConstraint("person_id", "value", name="uq_person_alias"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    person_id: str = Field(foreign_key="person.id", index=True)
    value: str = Field(index=True)
    created_at: datetime = Field(default_factory=utcnow)


class TaskPerson(SQLModel, table=True):
    """Associates a task with 0..n people it involves."""

    __table_args__ = (UniqueConstraint("task_id", "person_id", name="uq_task_person"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    person_id: str = Field(foreign_key="person.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class TaskRequester(SQLModel, table=True):
    """Associates a task with 0..n people who requested it.

    Kept separate from ``TaskPerson`` (the people a task involves): who asked
    for the task is a distinct fact from who is involved in it, so the two link
    sets can differ.
    """

    __table_args__ = (UniqueConstraint("task_id", "person_id", name="uq_task_requester"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    person_id: str = Field(foreign_key="person.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class ItemPerson(SQLModel, table=True):
    """Associates a source item with 0..n people behind it."""

    __table_args__ = (UniqueConstraint("item_id", "person_id", name="uq_item_person"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    item_id: str = Field(foreign_key="sourceitem.id", index=True)
    person_id: str = Field(foreign_key="person.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)
