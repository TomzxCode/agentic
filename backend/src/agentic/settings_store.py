"""App settings: environment defaults overridden by rows in the ``setting`` table."""

from __future__ import annotations

from sqlmodel import Session, select

from .config import settings
from .models import Setting, utcnow

# Keys the Settings page can override. Values are strings (URLs / templates).
SESSION_LINK_KEYS = ("openchamber_url", "openchamber_session_path", "terminal_url_template")


def env_defaults() -> dict[str, str]:
    return {
        "openchamber_url": settings.openchamber_url,
        "openchamber_session_path": settings.openchamber_session_path,
        "terminal_url_template": settings.terminal_url_template,
    }


def get_overrides(session: Session) -> dict[str, str]:
    return {row.key: row.value for row in session.exec(select(Setting)).all() if row.key in SESSION_LINK_KEYS}


def get_settings(session: Session) -> dict[str, str]:
    effective = env_defaults()
    effective.update(get_overrides(session))
    return effective


def update_settings(session: Session, values: dict[str, str | None]) -> dict[str, str]:
    for key, value in values.items():
        if key not in SESSION_LINK_KEYS or value is None:
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
