"""SQLModel tables for checklist templates and the items they put on tasks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel

from .base import new_id, utcnow


class ChecklistTemplate(SQLModel, table=True):
    """A reusable checklist plus the rules that decide which tasks it applies to.

    ``rules`` is a list of condition dicts (``field``, ``op``, ``values``) that
    all have to match. ``items`` is the ordered list of item texts copied onto
    a task the first time it matches.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    description: str = ""
    rules: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    items: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ChecklistTemplateApplication(SQLModel, table=True):
    """One task's record that a template has already been applied to it.

    The row is what stops a template from re-adding an item the user deleted,
    or from duplicating the items every time the task is edited. It stays after
    the task stops matching, so a later re-match leaves the items in place.
    """

    __table_args__ = (UniqueConstraint("task_id", "template_id", name="uq_checklist_application"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    template_id: str = Field(foreign_key="checklisttemplate.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class ChecklistItem(SQLModel, table=True):
    """One checklist item on a task.

    A derived item carries the template it came from (so the UI can name it and
    evaluate whether the template still applies); a manual item has no template
    and always applies. Items are independent copies, editable and removable
    without touching the template.
    """

    id: str = Field(default_factory=new_id, primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    template_id: str | None = Field(default=None, foreign_key="checklisttemplate.id", index=True)
    text: str
    position: int = 0
    done: bool = False
    done_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
