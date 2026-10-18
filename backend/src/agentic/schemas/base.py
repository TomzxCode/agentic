"""Pydantic request/response models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _assume_utc(value: datetime | None) -> datetime | None:
    """Treat a naive datetime from a client as UTC (the column requires a tz)."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


UtcDateTime = Annotated[datetime, AfterValidator(_assume_utc)]
