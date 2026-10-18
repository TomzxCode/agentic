"""Coding-agent harnesses, driven over ACP (Agent Client Protocol).

Grouped into harness seeding/resolution, the ACP client, and run execution.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import structlog
from sqlmodel import Session, select

from ..config import settings
from ..models.agents import Harness
from ..models.system import Setting

log = structlog.get_logger(__name__)

HARNESS_PRESETS: list[dict[str, Any]] = [
    {
        "id": "opencode",
        "name": "OpenCode",
        "description": "OpenCode's built-in ACP server (`opencode acp`).",
        "command": "opencode",
        "args": ["acp"],
        "resume_command": "opencode --session {session}",
        "default_model_source": "~/.config/opencode/opencode.json#model",
    },
    {
        "id": "opencode2",
        "name": "OpenCode v2",
        "description": "OpenCode v2's built-in ACP server (`opencode2 acp`).",
        "command": "opencode2",
        "args": ["acp"],
        "resume_command": "opencode2 --session {session}",
        "default_model_source": "~/.config/opencode/opencode.json#model",
    },
    {
        "id": "pi",
        "name": "pi",
        "description": "The pi coding agent, via the pi-acp adapter.",
        "command": "pi-acp",
        "args": [],
        "resume_command": "pi --session {session}",
        "default_model_source": "~/.pi/agent/settings.json#{defaultProvider}/{defaultModel}",
    },
]
RESUME_DEFAULTS = {
    "opencode": "opencode --session {session}",
    "opencode2": "opencode2 --session {session}",
    "pi": "pi --session {session}",
}
MODEL_SOURCE_DEFAULTS = {
    preset["id"]: preset["default_model_source"] for preset in HARNESS_PRESETS if preset.get("default_model_source")
}
OPENCODE_DEFAULT_PREFERENCE = ("opencode2", "opencode")
OPENCODE_DEFAULT_MARKER = "harness_default_seeded"


def _preferred_opencode_default() -> str:
    for harness_id in OPENCODE_DEFAULT_PREFERENCE:
        if shutil.which(harness_id):
            return harness_id
    return OPENCODE_DEFAULT_PREFERENCE[-1]


def seed_harnesses(session: Session) -> None:
    """Create the built-in harness presets, pick a default, and backfill fields.

    Missing presets are inserted on every call, so upgrading adds new built-ins
    (for example ``opencode2``) to an existing database. Existing rows are never
    overwritten, so custom edits survive.
    """
    existing = {harness.id for harness in session.exec(select(Harness)).all()}
    changed = False
    for preset in HARNESS_PRESETS:
        if preset["id"] in existing:
            continue
        session.add(
            Harness(
                id=preset["id"],
                name=preset["name"],
                description=preset["description"],
                command=preset["command"],
                args=preset["args"],
                resume_command=preset.get("resume_command"),
                default_model_source=preset.get("default_model_source"),
                is_default=False,
            )
        )
        changed = True
    if changed:
        session.commit()
    _ensure_default_harness(session)
    # Backfill resume commands for harnesses created before the column existed.
    changed = False
    for harness in session.exec(select(Harness)).all():
        if not harness.resume_command:
            fallback = RESUME_DEFAULTS.get(harness.id) or RESUME_DEFAULTS.get(harness.name.lower())
            if fallback:
                harness.resume_command = fallback
                session.add(harness)
                changed = True
        if not harness.default_model_source:
            source = MODEL_SOURCE_DEFAULTS.get(harness.id)
            if source:
                harness.default_model_source = source
                session.add(harness)
                changed = True
    if changed:
        session.commit()


def _ensure_default_harness(session: Session) -> None:
    """Guarantee a single default harness, preferring installed OpenCode v2.

    Seeding picks the default once, and only while no default is set or the set
    one is an OpenCode variant, so a deliberate choice (including one made in
    Settings) is never overwritten.
    """
    current = session.exec(select(Harness).where(Harness.is_default == True)).first()  # noqa: E712
    if session.get(Setting, OPENCODE_DEFAULT_MARKER) is not None and current is not None:
        return
    if current is not None and current.id not in OPENCODE_DEFAULT_PREFERENCE:
        _mark_default_seeded(session)
        session.commit()
        return
    target = session.get(Harness, _preferred_opencode_default()) or session.exec(select(Harness)).first()
    if target is None:
        return
    for harness in session.exec(select(Harness)).all():
        want = harness.id == target.id
        if harness.is_default != want:
            harness.is_default = want
            session.add(harness)
    _mark_default_seeded(session)
    session.commit()


def _mark_default_seeded(session: Session) -> None:
    if session.get(Setting, OPENCODE_DEFAULT_MARKER) is None:
        session.add(Setting(key=OPENCODE_DEFAULT_MARKER, value="1"))


def get_harness(session: Session, harness_id: str | None) -> Harness:
    if harness_id:
        harness = session.get(Harness, harness_id)
        if harness is not None:
            return harness
    harness = session.exec(select(Harness).where(Harness.is_default == True)).first()  # noqa: E712
    if harness is None:
        harness = session.exec(select(Harness).where(Harness.name == settings.default_harness)).first()
    if harness is None:
        harness = session.exec(select(Harness)).first()
    if harness is None:
        raise RuntimeError("No harness configured")
    return harness


def harness_available(harness: Harness) -> tuple[bool, str]:
    path = shutil.which(harness.command)
    if not path:
        return False, f"`{harness.command}` not found on PATH"
    return True, path


MAX_MODEL_SOURCE_BYTES = 1_000_000


def _lookup(data: Any, path: str) -> Any:
    """Follow a dotted path into the parsed config, or None when it is absent."""
    for part in path.split("."):
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data


def _as_model_name(value: Any) -> str | None:
    """Render a model setting: a plain id, or an object naming provider and model.

    OpenCode accepts ``"model": "provider/model"`` and
    ``"model": {"providerID": ..., "model": ...}``; both read as "provider/model".
    """
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        provider = value.get("providerID") or value.get("provider")
        name = value.get("model") or value.get("id") or value.get("name")
        if provider and name:
            return f"{provider}/{name}"
    return None


def resolve_default_model(harness: Harness) -> str | None:
    """The model a harness uses on its own, read from its config file.

    A run that selects no model gets whatever the harness resolves; reading the
    harness's own config file says what that is without spawning it (about 1.7 s
    over ACP). ``default_model_source`` is ``<json file>#<template>``: the
    template's ``{dotted.path}`` placeholders are filled from the file's top
    level, and a template without braces is one path. Anything unreadable, absent
    or of the wrong shape resolves to None, so the display says nothing rather
    than guessing.

    The value is the user-level default. A project config in the run's cwd, and
    the harness's own fallback when the file names no model, are not visible from
    here.
    """
    source = (harness.default_model_source or "").strip()
    path, separator, template = source.partition("#")
    if not separator or not path.strip() or not template.strip():
        return None
    try:
        file = Path(path.strip()).expanduser()
        if file.stat().st_size > MAX_MODEL_SOURCE_BYTES:
            return None
        data = json.loads(file.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if "{" not in template:
        return _as_model_name(_lookup(data, template.strip()))
    missing = False

    def fill(match: re.Match[str]) -> str:
        nonlocal missing
        value = _lookup(data, match.group(1).strip())
        if not isinstance(value, (str, int, float)) or str(value) == "":
            missing = True
            return ""
        return str(value)

    filled = re.sub(r"\{([^{}]+)\}", fill, template)
    return None if missing else filled
