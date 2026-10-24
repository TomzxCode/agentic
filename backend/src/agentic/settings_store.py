"""App settings: environment defaults overridden by rows in the ``setting`` table."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, col, select

from .config import settings
from .models.base import utcnow
from .models.system import Setting
from .refresh import REFRESHABLE_SOURCES
from .services.github import detect_github_login

log = structlog.get_logger(__name__)

# Keys the Settings page can override. Values are strings (URLs, templates, and
# JSON-encoded lists such as ``agent_prompts``).
OVERRIDABLE_KEYS = (
    "github_login",
    "openchamber_url",
    "openchamber_session_path",
    "terminal_url_template",
    "editor_url_template",
    "ghx_url",
    "slackx_url",
    "ghx_backend",
    "ghx_rpc_url",
    "ghx_rpc_token",
    "slackx_backend",
    "slackx_rpc_url",
    "slackx_rpc_token",
    "slack_refresh_policy",
    "slack_user_id",
    "slack_bot_token",
    "slack_events_user_id",
    "slack_events_channel",
    "slack_notify_user_id",
    "github_refresh_policy",
    "review_scan_interval",
    "review_scan_default",
    "review_slo",
    "agent_prompts",
    "on_call_channel",
    "on_call_config",
)

# The item kinds a user-defined agent prompt can target. A prompt appears in the
# agent panel only when the task has exactly one associated item of its kind.
AGENT_PROMPT_KINDS = ("issue", "pull_request")

# Seeded prompt buttons: one to review a pull request, one to triage an issue.
# The SPA substitutes the prompt's variables (``{owner}``, ``{repository}``,
# ``{number}``, and the task's own fields) before the run starts.
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
        "ghx_url": settings.ghx_url,
        "slackx_url": settings.slackx_url,
        "ghx_backend": settings.ghx_backend,
        "ghx_rpc_url": settings.ghx_rpc_url,
        "ghx_rpc_token": settings.ghx_rpc_token,
        "slackx_backend": settings.slackx_backend,
        "slackx_rpc_url": settings.slackx_rpc_url,
        "slackx_rpc_token": settings.slackx_rpc_token,
        "slack_refresh_policy": settings.slack_refresh_policy,
        "slack_user_id": settings.slack_user_id,
        "slack_bot_token": settings.slack_bot_token,
        "slack_events_user_id": settings.slack_events_user_id,
        "slack_events_channel": settings.slack_events_channel,
        "slack_notify_user_id": settings.slack_notify_user_id,
        "github_refresh_policy": settings.github_refresh_policy,
        "review_scan_interval": settings.review_scan_interval,
        "review_scan_default": settings.review_scan_default,
        "review_slo": settings.review_slo,
        "agent_prompts": json.dumps(DEFAULT_AGENT_PROMPTS),
    }


def get_overrides(session: Session) -> dict[str, str]:
    return {row.key: row.value for row in session.exec(select(Setting)).all() if row.key in OVERRIDABLE_KEYS}


# The transport keys for the ghx and slackx helper CLIs. They decide how the
# server runs those tools ("cli" spawns the binary, "rpc" calls its JSON-RPC
# server), so they are read per call by ``services.shell``, which has no
# session of its own.
RPC_SETTING_KEYS = (
    "ghx_backend",
    "ghx_rpc_url",
    "ghx_rpc_token",
    "slackx_backend",
    "slackx_rpc_url",
    "slackx_rpc_token",
)


def get_rpc_overrides() -> dict[str, str]:
    """The stored rpc transport overrides, read fresh from the setting table.

    Opens its own session: the callers resolve the transport deep inside the
    fetchers (and from the worker), where no request session is at hand. A
    store that is not there yet (before the first migration) reads as no
    overrides; anything else raises, and the caller falls back to the
    environment values.
    """
    from .db import engine

    try:
        with Session(engine) as session:
            rows = session.exec(select(Setting).where(col(Setting.key).in_(RPC_SETTING_KEYS))).all()
    except OperationalError:
        log.debug("rpc settings store not ready")
        return {}
    return {row.key: row.value for row in rows if row.value is not None}


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


# How far back a source keeps its run history, so the Settings page can sum a
# trailing window ("X refreshed in the last 24h") without the row growing
# without bound. Runs older than the window are dropped as new ones land.
REFRESH_HISTORY_WINDOW = timedelta(hours=24)


def _history_time(entry: object) -> datetime | None:
    """The timestamp of a history entry, or None when it is malformed."""
    if not isinstance(entry, dict):
        return None
    try:
        parsed = datetime.fromisoformat(str(entry.get("at")))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _prune_history(history: list[dict], now: datetime) -> list[dict]:
    """Keep only the runs within the history window, oldest first."""
    reference = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    cutoff = reference - REFRESH_HISTORY_WINDOW
    kept: list[dict] = []
    for entry in history:
        at = _history_time(entry)
        if at is not None and at >= cutoff:
            kept.append(entry)
    return kept


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
    """Persist a source's last refresh pass and append it to its run history."""
    key = refresh_status_key(source)
    row = session.get(Setting, key)
    history: list[dict] = []
    if row is not None and row.value:
        try:
            previous = json.loads(row.value)
        except json.JSONDecodeError:
            previous = {}
        if isinstance(previous, dict) and isinstance(previous.get("history"), list):
            history = previous["history"]
    history.append({"at": last_run_at.isoformat(), "refreshed": refreshed, "failed": failed})
    value = json.dumps(
        {
            "last_run_at": last_run_at.isoformat(),
            "refreshed": refreshed,
            "failed": failed,
            "error": error[:300] if error else None,
            "origin": origin,
            "history": _prune_history(history, last_run_at),
        }
    )
    if row is None:
        row = Setting(key=key, value=value)
    else:
        row.value = value
        row.updated_at = utcnow()
    session.add(row)
    session.commit()


def _refreshed_within_window(data: dict, cutoff: datetime) -> int:
    """Items refreshed in the last window, from the run history or the last run.

    A row written before histories were kept has none, so its single last run
    counts when it falls inside the window.
    """
    history = data.get("history")
    if not isinstance(history, list):
        at = _history_time({"at": data.get("last_run_at")})
        return int(data.get("refreshed") or 0) if at is not None and at >= cutoff else 0
    total = 0
    for entry in history:
        at = _history_time(entry)
        if at is not None and at >= cutoff:
            total += int(entry.get("refreshed") or 0)
    return total


def get_refresh_status(session: Session) -> dict[str, dict]:
    """Read each source's last refresh pass, skipping unset or unreadable ones.

    Each status also carries ``refreshed_24h``: the items refreshed across the
    runs of the last day, summed from the stored history.
    """
    rows = {row.key: row.value for row in session.exec(select(Setting)).all()}
    cutoff = utcnow() - REFRESH_HISTORY_WINDOW
    status: dict[str, dict] = {}
    for source in REFRESHABLE_SOURCES:
        raw = rows.get(refresh_status_key(source))
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            data["refreshed_24h"] = _refreshed_within_window(data, cutoff)
        status[source] = data
    return status


# The review scan's last pass. Kept out of OVERRIDABLE_KEYS: it is the job's own
# state, not something the Settings page edits.
REVIEW_SCAN_STATUS_KEY = "review_scan_status"


def record_review_scan_run(
    session: Session,
    *,
    last_run_at: datetime,
    found: int,
    stored: int,
    error: str | None = None,
    origin: str = "background",
) -> None:
    """Persist the review scan's last pass, so the Settings page can show it."""
    value = json.dumps(
        {
            "last_run_at": last_run_at.isoformat(),
            "found": found,
            "stored": stored,
            "error": error[:300] if error else None,
            "origin": origin,
        }
    )
    row = session.get(Setting, REVIEW_SCAN_STATUS_KEY)
    if row is None:
        row = Setting(key=REVIEW_SCAN_STATUS_KEY, value=value)
    else:
        row.value = value
        row.updated_at = utcnow()
    session.add(row)
    session.commit()


def get_review_scan_status(session: Session) -> dict:
    """The review scan's last pass, or an empty dict when it never ran."""
    row = session.get(Setting, REVIEW_SCAN_STATUS_KEY)
    if row is None or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except json.JSONDecodeError:
        return {}
