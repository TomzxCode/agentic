"""App settings that override environment defaults (session links, refresh)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..diagnostics import collect_diagnostics
from ..refresh import POLICY_SETTING_KEYS, PolicyError, describe_policy, parse_policy
from ..review_scan import scan_interval
from ..schemas.settings import (
    DiagnosticsRead,
    RefreshPolicyPreview,
    RefreshPolicyPreviewRequest,
    RefreshStatusRead,
    SettingsRead,
    SettingsUpdate,
)
from ..services.managed_tools import managed_tools
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
    interval = values.get("review_scan_interval")
    if interval is not None and interval.strip() and scan_interval(interval) is None:
        raise HTTPException(
            status_code=422,
            detail="review_scan_interval: use a duration such as 30m, 1h or 1d, or leave it blank to stop scanning",
        )
    scan_default = values.get("review_scan_default")
    if scan_default is not None and scan_default not in ("include", "exclude"):
        raise HTTPException(status_code=422, detail="review_scan_default: must be include or exclude")
    for key in ("ghx_backend", "slackx_backend"):
        backend = values.get(key)
        if backend is not None and backend not in ("cli", "rpc", "managed"):
            raise HTTPException(status_code=422, detail=f"{key}: must be cli, rpc or managed")
    for key in ("ghx_rpc_url", "slackx_rpc_url"):
        url = values.get(key)
        if url and not url.startswith(("http://", "https://")):
            raise HTTPException(status_code=422, detail=f"{key}: must be an http(s) URL")
    slo = values.get("review_slo")
    if slo is not None and slo.strip() and scan_interval(slo) is None:
        raise HTTPException(
            status_code=422,
            detail="review_slo: use a duration such as 8h or 1d, or leave it blank to turn it off",
        )
    prompts = values.get("agent_prompts")
    if prompts is not None:
        try:
            parse_agent_prompts(prompts)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"agent_prompts: {exc}") from exc
    update_settings(session, values)
    if any(key in values for key in ("ghx_backend", "slackx_backend")):
        # A switch to or from managed starts or stops the tool's serve process,
        # so the change applies without a restart.
        managed_tools.sync()
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


@router.get("/diagnostics", response_model=DiagnosticsRead)
def read_diagnostics(session: Session = Depends(get_session)) -> DiagnosticsRead:
    """Presence and versions of the external tools and harnesses the app uses.

    Sync on purpose: FastAPI runs it in a worker thread, so the version probes
    never block the event loop.
    """
    return collect_diagnostics(session)


__all__ = ["router"]
