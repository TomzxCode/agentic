"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime

from .base import ORMModel


class OperationRead(ORMModel):
    """One row of the operations audit log."""

    id: str
    method: str
    path: str
    status_code: int
    client: str
    actor: str
    created_at: datetime
