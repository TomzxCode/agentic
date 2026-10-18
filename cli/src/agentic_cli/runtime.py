"""Shared CLI runtime: context, output format, and the API client."""

from __future__ import annotations

import functools
import json
import os
import sys
from typing import Any, Literal

from .client import DEFAULT_API_URL, AgenticClient, ApiError

CONTEXT: dict[str, Any] = {
    "api_url": os.environ.get("AGENTIC_API_URL", DEFAULT_API_URL),
    "format": os.environ.get("AGENTIC_FORMAT", "auto"),
    "timeout": float(os.environ.get("AGENTIC_TIMEOUT", "60")),
    # Who is driving the CLI. The harness sets AGENTIC_ACTOR=agent for the agent
    # process it spawns, so the server can tell agent work from human work.
    "actor": os.environ.get("AGENTIC_ACTOR", "human"),
}

TaskStatus = Literal["open", "in_progress", "blocked", "done", "archived"]

Source = Literal["slack", "github", "gdrive", "url", "note", "commit", "file"]

ChangeStatusArg = Literal["proposed", "verified", "accepted", "rejected", "reverted"]

ChangeClassArg = Literal["feature", "bugfix", "refactor", "chore", "docs", "test", "trivial"]

InterventionArg = Literal["question", "correction", "manual_fix", "rerun", "approval", "other"]


def _resolve_format() -> str:
    fmt = CONTEXT["format"]
    if fmt == "auto":
        return "text" if sys.stdout.isatty() else "json"
    return fmt


def emit(data: Any, text: str | None = None) -> str:
    if _resolve_format() == "json":
        return json.dumps(data, indent=2, default=str)
    return text if text is not None else json.dumps(data, indent=2, default=str)


def _client() -> AgenticClient:
    return AgenticClient(CONTEXT["api_url"], timeout=CONTEXT["timeout"], actor=CONTEXT["actor"])


def safe(fn):
    """Turn API errors into a one-line stderr message and a non-zero exit code."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ApiError as exc:
            print(f"error: {exc.detail} (HTTP {exc.status_code})", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("interrupted", file=sys.stderr)
            return 130

    return wrapper
