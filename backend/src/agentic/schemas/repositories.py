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
    # One of ReviewScanPolicy: whether the review scan considers this
    # repository's pull requests.
    review_scan: str = "default"
    created_at: datetime


class RepositoryUpdate(BaseModel):
    """The repository fields the app lets a client change."""

    review_scan: str | None = None


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
