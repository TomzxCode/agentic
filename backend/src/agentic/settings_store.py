"""App settings: environment defaults overridden by rows in the ``setting`` table."""

from __future__ import annotations

import json
from datetime import datetime

from sqlmodel import Session, select

from .config import settings
from .models import Setting, utcnow
from .refresh import REFRESHABLE_SOURCES
from .services import detect_github_login

# Keys the Settings page can override. Values are strings (URLs, templates, and
# JSON-encoded lists such as ``agent_prompts``).
OVERRIDABLE_KEYS = (
    "github_login",
    "openchamber_url",
    "openchamber_session_path",
    "terminal_url_template",
    "editor_url_template",
    "slack_refresh_policy",
    "github_refresh_policy",
    "agent_prompts",
)

# The item kinds a user-defined agent prompt can target. A prompt appears in the
# agent panel only when the task has exactly one associated item of its kind.
AGENT_PROMPT_KINDS = ("issue", "pull_request")

# Seeded prompt buttons: one to review a pull request, one to triage an issue.
# ``{owner}``, ``{repository}``, and ``{number}`` are substituted from the
# associated GitHub item before the run starts.
DEFAULT_AGENT_PROMPTS: list[dict[str, str]] = [
    {"kind": "pull_request", "label": "Review PR", "template": "$review-pr-full {number} {owner}/{repository}"},
    {"kind": "issue", "label": "Triage issue", "template": "$triage-issue {number} {owner}/{repository}"},
]


def parse_agent_prompts(raw: str) -> list[dict[str, str]]:
    """Validate the JSON list of user-defined prompts. Raises ``ValueError``."""
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("must be a JSON list of prompts")
    prompts: list[dict[str, str]] = []
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("each prompt must be an object")
        kind = entry.get("kind")
        if kind not in AGENT_PROMPT_KINDS:
            raise ValueError(f"prompt kind must be one of {', '.join(AGENT_PROMPT_KINDS)}")
        template = str(entry.get("template") or "").strip()
        if not template:
            raise ValueError("prompt template is required")
        prompts.append({"kind": kind, "label": str(entry.get("label") or ""), "template": template})
    return prompts


def env_defaults() -> dict[str, str]:
    return {
        "github_login": settings.github_login,
        "openchamber_url": settings.openchamber_url,
        "openchamber_session_path": settings.openchamber_session_path,
        "terminal_url_template": settings.terminal_url_template,
        "editor_url_template": settings.editor_url_template,
        "slack_refresh_policy": settings.slack_refresh_policy,
        "github_refresh_policy": settings.github_refresh_policy,
        "agent_prompts": json.dumps(DEFAULT_AGENT_PROMPTS),
    }


def get_overrides(session: Session) -> dict[str, str]:
    return {row.key: row.value for row in session.exec(select(Setting)).all() if row.key in OVERRIDABLE_KEYS}


def get_settings(session: Session) -> dict[str, str]:
    effective = env_defaults()
    effective.update(get_overrides(session))
    # No login configured anywhere? Fall back to the authenticated `gh` account,
    # so the identity works without the user setting anything.
    if not effective.get("github_login", "").strip():
        detected = detect_github_login()
        if detected:
            effective["github_login"] = detected
    return effective


def resolve_github_login(session: Session) -> str:
    """The GitHub login that counts as the user, or "" when none is known."""
    return get_settings(session).get("github_login", "").strip()


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
