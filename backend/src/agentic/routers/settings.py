"""App settings that override environment defaults (session links)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..db import get_session
from ..schemas import SettingsRead, SettingsUpdate
from ..settings_store import env_defaults, get_overrides, get_settings, update_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _read(session: Session) -> SettingsRead:
    return SettingsRead(
        effective=get_settings(session),
        overrides=get_overrides(session),
        defaults=env_defaults(),
    )


@router.get("", response_model=SettingsRead)
def read_settings(session: Session = Depends(get_session)) -> SettingsRead:
    return _read(session)


@router.patch("", response_model=SettingsRead)
def patch_settings(payload: SettingsUpdate, session: Session = Depends(get_session)) -> SettingsRead:
    update_settings(session, payload.model_dump(exclude_unset=True))
    return _read(session)
