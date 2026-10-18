"""Pydantic request/response models."""

from __future__ import annotations

from pydantic import BaseModel


class WorktreeCreate(BaseModel):
    repository_id: str | None = None
    branch: str | None = None
    base: str | None = None
