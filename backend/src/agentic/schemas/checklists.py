"""Request/response models for checklist templates and task checklist items."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .base import ORMModel


class ChecklistRule(BaseModel):
    """One condition in a template's match rules.

    ``field`` names a task property, ``op`` says how to compare it, and
    ``values`` holds the ids or names to compare against. The router validates
    the vocabulary on write; the matcher also fails closed on an unknown field
    or operator, so a rule written by a newer version never matches by accident.
    """

    field: str
    op: str
    values: list[str | int] = []


class ChecklistTemplateCreate(BaseModel):
    name: str
    description: str = ""
    rules: list[ChecklistRule] = []
    items: list[str] = []


class ChecklistTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    rules: list[ChecklistRule] | None = None
    items: list[str] | None = None


class ChecklistTemplateRead(ORMModel):
    id: str
    name: str
    description: str
    rules: list[ChecklistRule]
    items: list[str]
    created_at: datetime
    updated_at: datetime
    # How many tasks have had this template applied to them.
    applied_count: int = 0


class ChecklistItemCreate(BaseModel):
    text: str
    position: int | None = None


class ChecklistItemUpdate(BaseModel):
    text: str | None = None
    done: bool | None = None


class ChecklistItemRead(ORMModel):
    id: str
    task_id: str
    template_id: str | None = None
    # The template's name, so a task can label a derived item without a lookup.
    template_name: str | None = None
    text: str
    position: int
    done: bool
    done_at: datetime | None = None
    # False when the item came from a template whose rules no longer match the
    # task. The item stays, shown disabled, so a completed step is not lost.
    applicable: bool = True
    created_at: datetime
    updated_at: datetime


class ChecklistApplyResult(BaseModel):
    """How many tasks an apply pass changed."""

    applied: int = 0
