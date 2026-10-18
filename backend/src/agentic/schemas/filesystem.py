"""Pydantic request/response models."""

from __future__ import annotations

from pydantic import BaseModel


class FsEntry(BaseModel):
    name: str
    path: str
    is_git: bool = False


class FsListing(BaseModel):
    root: str
    path: str
    parent: str | None = None
    is_git: bool = False
    entries: list[FsEntry] = []
