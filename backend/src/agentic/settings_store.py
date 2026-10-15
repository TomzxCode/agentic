"""App settings: environment defaults overridden by rows in the ``setting`` table."""

from __future__ import annotations

import json
from datetime import datetime

from sqlmodel import Session, select

from .config import settings
from .models import Setting, utcnow
from .refresh import REFRESHABLE_SOURCES

# Keys the Settings page can override. Values are strings (URLs / templates).
OVERRIDABLE_KEYS = (
    "openchamber_url",
    "openchamber_session_path",
    "terminal_url_template",
    "editor_url_template",
    "slack_refresh_policy",
    "github_refresh_policy",
)


def env_defaults() -> dict[str, str]:
    return {
        "openchamber_url": settings.openchamber_url,
        "openchamber_session_path": settings.openchamber_session_path,
        "terminal_url_template": settings.terminal_url_template,
        "editor_url_template": settings.editor_url_template,
        "slack_refresh_policy": settings.slack_refresh_policy,
        "github_refresh_policy": settings.github_refresh_policy,
    }


def get_overrides(session: Session) -> dict[str, str]:
    return {row.key: row.value for row in session.exec(select(Setting)).all() if row.key in OVERRIDABLE_KEYS}


def get_settings(session: Session) -> dict[str, str]:
    effective = env_defaults()
    effective.update(get_overrides(session))
    return effective


def update_settings(session: Session, values: dict[str, str | None]) -> dict[str, str]:
    for key, value in values.items():
        if key not in OVERRIDABLE_KEYS or value is None:
            continue
        row = session.get(Setting, key)
        if row is None:
            row = Setting(key=key, value=value)
        else:
            row.value = value
            row.updated_at = utcnow()
        session.add(row)
    session.commit()
    return get_settings(session)


def refresh_status_key(source: str) -> str:
    """The non-overridable setting key holding a source's last background run."""
    return f"{source}_refresh_status"


def record_refresh_run(
    session: Session,
    source: str,
    *,
    last_run_at: datetime,
    refreshed: int,
    failed: int = 0,
    error: str | None = None,
    origin: str = "background",
) -> None:
    """Persist a source's last refresh pass (invisible to the settings API)."""
    key = refresh_status_key(source)
    value = json.dumps(
        {
            "last_run_at": last_run_at.isoformat(),
            "refreshed": refreshed,
            "failed": failed,
            "error": error[:300] if error else None,
            "origin": origin,
        }
    )
    row = session.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=value)
    else:
        row.value = value
        row.updated_at = utcnow()
    session.add(row)
    session.commit()


def get_refresh_status(session: Session) -> dict[str, dict]:
    """Read each source's last refresh pass, skipping unset or unreadable ones."""
    rows = {row.key: row.value for row in session.exec(select(Setting)).all()}
    status: dict[str, dict] = {}
    for source in REFRESHABLE_SOURCES:
        raw = rows.get(refresh_status_key(source))
        if not raw:
            continue
        try:
            status[source] = json.loads(raw)
        except json.JSONDecodeError:
            continue
    return status
