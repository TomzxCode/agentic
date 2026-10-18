"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .base import ORMModel


class RepositoryCreate(BaseModel):
    name: str | None = None
    path: str
    remote_url: str | None = None
    default_branch: str | None = None


class RepositoryBulkCreate(BaseModel):
    paths: list[str]


class RepositoryRead(ORMModel):
    id: str
    name: str
    path: str
    remote_url: str | None = None
    default_branch: str | None = None
    created_at: datetime


class RepositoryBulkResult(BaseModel):
    added: list[RepositoryRead] = []
    errors: list[dict[str, str]] = []


class RepositoryGroupCreate(BaseModel):
    name: str
    description: str = ""
    repository_ids: list[str] = []


class RepositoryGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    repository_ids: list[str] | None = None


class RepositoryGroupRead(ORMModel):
    id: str
    name: str
    description: str
    repository_ids: list[str] = []
    created_at: datetime
