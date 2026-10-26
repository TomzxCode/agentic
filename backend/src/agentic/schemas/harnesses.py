"""Pydantic request/response models."""

from __future__ import annotations

from pydantic import BaseModel

from .base import ORMModel


class HarnessCreate(BaseModel):
    name: str
    description: str = ""
    command: str
    args: list[str] = []
    env: dict[str, str] = {}
    model: str | None = None
    default_model_source: str | None = None
    resume_command: str | None = None
    is_default: bool = False


class HarnessUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    model: str | None = None
    default_model_source: str | None = None
    resume_command: str | None = None
    is_default: bool | None = None


class HarnessRead(ORMModel):
    id: str
    name: str
    description: str
    command: str
    args: list[str]
    env: dict[str, str]
    model: str | None = None
    default_model_source: str | None = None
    # The model the harness config file names, resolved for display. Read only.
    default_model: str | None = None
    resume_command: str | None = None
    is_default: bool


class HarnessStatus(BaseModel):
    id: str
    name: str
    available: bool
    detail: str = ""
    is_default: bool = False
    model: str | None = None
    default_model: str | None = None


class HarnessModelChoice(BaseModel):
    value: str
    name: str


class HarnessModelsRead(BaseModel):
    """The models a harness offers, read from a live ACP session.

    ``live`` says the answer came from a session the API holds open; every
    harness gets one held and reused, so any answered request is live. ``error``
    is set when the harness could not be asked, so the caller shows why rather
    than an empty list.
    """

    harness_id: str
    models: list[HarnessModelChoice] = []
    current: str | None = None
    live: bool = False
    error: str | None = None
