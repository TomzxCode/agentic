"""Side-effectful helpers, grouped by purpose."""

from __future__ import annotations

import re
from pathlib import Path

GITHUB_RE = re.compile(r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<kind>issues|pull)/(?P<num>\d+)")


SLACK_RE = re.compile(r"https://(?P<workspace>[^./]+)\.slack\.com/archives/(?P<channel>[^/]+)/p(?P<ts>\d+)")


def parse_github(url: str) -> dict[str, str] | None:
    match = GITHUB_RE.search(url or "")
    if not match:
        return None
    kind = "pull_request" if match.group("kind") == "pull" else "issue"
    return {
        "owner": match.group("owner"),
        "repo": match.group("repo"),
        "kind": kind,
        "number": match.group("num"),
        "external_id": f"{match.group('owner')}/{match.group('repo')}#{match.group('num')}",
    }


def parse_slack(url: str) -> dict[str, str] | None:
    match = SLACK_RE.search(url or "")
    if not match:
        return None
    ts = match.group("ts")
    return {
        "channel": match.group("channel"),
        "ts": f"{ts[:10]}.{ts[10:]}",
        "workspace": match.group("workspace"),
        "external_id": f"{match.group('channel')}:{ts}",
    }


GOOGLE_DOC_RE = re.compile(r"https?://(?:docs|drive)\.google\.com/[^/]+/d/([A-Za-z0-9_-]+)")


URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://\S+$")


BARE_HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?(?:\.[a-z0-9\-]+)+(?:[/?#]\S*)?$", re.IGNORECASE)


def looks_like_url(value: str | None) -> bool:
    """True when the value looks like a URL (scheme, or a bare domain)."""
    text = (value or "").strip()
    if not text or any(char.isspace() for char in text):
        return False
    return bool(URL_SCHEME_RE.match(text) or BARE_HOST_RE.match(text))


# A filesystem path the user typed: absolute, home-relative, explicit relative,
# a Windows drive, or a UNC share. A relative path without a marker is only
# taken as a path when it exists on the server.
PATH_PREFIX_RE = re.compile(r"^(?:~[/\\]|/|\.{1,2}[/\\]|[A-Za-z]:[/\\]|\\\\)")


def _strip_file_scheme(text: str) -> str:
    if text.lower().startswith("file://"):
        return text[7:]
    return text


def looks_like_path(value: str | None) -> bool:
    """True when the value is a filesystem path rather than a URL or text."""
    text = _strip_file_scheme((value or "").strip())
    if not text or "\n" in text or "\r" in text:
        return False
    if looks_like_url(text):
        return False
    if PATH_PREFIX_RE.match(text):
        return True
    # A bare relative path is ambiguous with prose, so only an existing one counts.
    try:
        return Path(text).expanduser().exists()
    except (OSError, ValueError):
        return False


def parse_path(value: str | None) -> dict[str, str] | None:
    """Resolve a typed path to an absolute path and its kind.

    A missing path is still returned (with an empty kind), so a reference to a
    file that is not there yet can be captured; a fetch reports it as missing.
    """
    text = _strip_file_scheme((value or "").strip())
    if not looks_like_path(text):
        return None
    try:
        path = Path(text).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    kind = "directory" if path.is_dir() else "file" if path.is_file() else ""
    return {"path": str(path), "kind": kind}
