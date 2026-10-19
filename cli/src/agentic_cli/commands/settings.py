"""CLI commands."""

from __future__ import annotations

from typing import Any

from cyclopts import App

from .. import runtime
from ..runtime import (
    emit,
    safe,
)

settings_app = App(name="settings", help="Read and update app settings.")


def register(app: App) -> None:
    app.command(settings_app)


@settings_app.command(name="get")
@safe
def settings_get() -> str:
    """Show effective settings and their overrides."""
    with runtime._client() as client:
        settings = client.get_settings()
    effective = settings["effective"]
    text = "\n".join(f"{key} = {value!r}" for key, value in effective.items())
    return emit(settings, text)


@settings_app.command(name="refresh-status")
@safe
def settings_refresh_status() -> str:
    """Show when the background refresh job last ran for each source."""
    with runtime._client() as client:
        status = client.refresh_status()
    sources = status.get("sources") or {}
    lines = [
        f"{source}: {entry.get('last_run_at') or 'never'}  ({entry.get('refreshed', 0)} refreshed, "
        f"{entry.get('refreshed_24h', 0)} in the last 24h)"
        for source, entry in sources.items()
    ]
    return emit(status, "\n".join(lines) or "no background runs recorded")


@settings_app.command(name="set")
@safe
def settings_set(
    openchamber_url: str | None = None,
    openchamber_session_path: str | None = None,
    terminal_url_template: str | None = None,
    slack_refresh_policy: str | None = None,
    github_refresh_policy: str | None = None,
) -> str:
    """Override settings (empty disables a link or a source's refresh; policies look like 1d=1h,7d=6h,30d=1d,*=7d)."""
    values: dict[str, Any] = {
        "openchamber_url": openchamber_url,
        "openchamber_session_path": openchamber_session_path,
        "terminal_url_template": terminal_url_template,
        "slack_refresh_policy": slack_refresh_policy,
        "github_refresh_policy": github_refresh_policy,
    }
    with runtime._client() as client:
        settings = client.update_settings(**values)
    effective = settings["effective"]
    text = "\n".join(f"{key} = {value!r}" for key, value in effective.items())
    return emit(settings, text)
