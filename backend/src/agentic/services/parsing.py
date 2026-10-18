"""Side-effectful helpers, grouped by purpose."""

from __future__ import annotations

import re

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
