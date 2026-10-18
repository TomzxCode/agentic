"""App settings that override environment defaults (session links, refresh)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..refresh import POLICY_SETTING_KEYS, PolicyError, describe_policy, parse_policy
from ..schemas.settings import (
    RefreshPolicyPreview,
    RefreshPolicyPreviewRequest,
    RefreshStatusRead,
    SettingsRead,
    SettingsUpdate,
)
from ..settings_store import (
    env_defaults,
    get_overrides,
    get_refresh_status,
    get_settings,
    parse_agent_prompts,
    update_settings,
)

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
    values = payload.model_dump(exclude_unset=True)
    for key in POLICY_SETTING_KEYS.values():
        policy_text = values.get(key)
        if policy_text is None:
            continue
        try:
            parse_policy(policy_text)
        except PolicyError as exc:
            raise HTTPException(status_code=422, detail=f"{key}: {exc}") from exc
    prompts = values.get("agent_prompts")
    if prompts is not None:
        try:
            parse_agent_prompts(prompts)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"agent_prompts: {exc}") from exc
    update_settings(session, values)
    return _read(session)


@router.post("/refresh-policy/preview", response_model=RefreshPolicyPreview)
def preview_refresh_policy(payload: RefreshPolicyPreviewRequest) -> RefreshPolicyPreview:
    """Parse a refresh policy so the UI can show its bands before saving."""
    try:
        return RefreshPolicyPreview.model_validate(describe_policy(payload.value))
    except PolicyError as exc:
        return RefreshPolicyPreview(valid=False, error=str(exc))


@router.get("/refresh-status", response_model=RefreshStatusRead)
def read_refresh_status(session: Session = Depends(get_session)) -> RefreshStatusRead:
    """When the background refresh job last ran for each source."""
    return RefreshStatusRead(sources=get_refresh_status(session))


__all__ = ["router"]
