"""Side-effectful helpers, grouped by purpose."""

from __future__ import annotations

import re
from typing import Any

import httpx
import structlog

from .github import _fetch_github
from .parsing import GOOGLE_DOC_RE, looks_like_url, parse_github, parse_slack
from .slack import _fetch_slack

log = structlog.get_logger(__name__)


def infer_item_source(
    url: str | None = None,
    external_id: str | None = None,
    content: str | None = None,
) -> dict[str, str | None]:
    """Work out an item's source/kind/external id from what the user provided.

    Lets callers omit the source entirely: a GitHub or Slack link, a Google
    Docs/Drive link, another URL, or plain text each map to the right source.
    Plain text that is not a URL (or bare content) becomes a note.
    """
    text = (url or "").strip()
    if text and looks_like_url(text):
        github = parse_github(text)
        if github:
            return {"source": "github", "kind": github["kind"], "external_id": github["external_id"]}
        slack = parse_slack(text)
        if slack:
            return {"source": "slack", "kind": "thread", "external_id": slack["external_id"]}
        google = GOOGLE_DOC_RE.search(text)
        if google:
            return {"source": "gdrive", "kind": "doc", "external_id": google.group(1)}
        return {"source": "url", "kind": "", "external_id": external_id}
    return {"source": "note", "kind": "", "external_id": external_id}


def fetch_source(source: str, url: str | None, external_id: str | None, title: str) -> dict[str, Any]:
    """Best-effort metadata/content pull. Never raises.

    ``error`` is set when the underlying fetch could not run (a missing or
    failing CLI, an unreachable URL) so a caller can surface the failure rather
    than treating empty output as a successful refresh.
    """

    result: dict[str, Any] = {"metadata": {}, "content": "", "title": title, "people": [], "error": None}
    try:
        if source == "github" and url:
            _fetch_github(url, result)
        elif source == "slack" and url:
            _fetch_slack(url, result)
        elif url and (source in ("url", "gdrive") or source == "web"):
            _fetch_url(url, result)
    except Exception as exc:  # noqa: BLE001
        log.info("fetch_source failed", source=source, url=url, error=str(exc))
        result["error"] = f"could not fetch {url or source}: {exc}"
    return result


def _fetch_url(url: str, result: dict[str, Any]) -> None:
    response = httpx.get(url, follow_redirects=True, timeout=20, headers={"User-Agent": "agentic/0.1"})
    response.raise_for_status()
    html = response.text
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    if title_match and not result["title"]:
        result["title"] = re.sub(r"\s+", " ", title_match.group(1)).strip()
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    result["content"] = body[:20_000]
