"""Side-effectful helpers, grouped by purpose."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import structlog

from .github import _fetch_github
from .parsing import GOOGLE_DOC_RE, looks_like_url, parse_github, parse_path, parse_slack
from .slack import _fetch_slack

log = structlog.get_logger(__name__)

# How much of a file or directory listing is kept as an item's content.
_PATH_CONTENT_LIMIT = 20_000
_PATH_LISTING_LIMIT = 500


def infer_item_source(
    url: str | None = None,
    external_id: str | None = None,
    content: str | None = None,
    path: str | None = None,
) -> dict[str, str | None]:
    """Work out an item's source/kind/external id from what the user provided.

    Lets callers omit the source entirely: a GitHub or Slack link, a Google
    Docs/Drive link, another URL, a local file or directory path, or plain text
    each map to the right source. Plain text that is not a URL becomes a note.
    """
    typed_path = parse_path(path or url)
    if typed_path:
        return {
            "source": "file",
            "kind": typed_path["kind"],
            "external_id": typed_path["path"],
            "path": typed_path["path"],
        }
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


def fetch_source(
    source: str,
    url: str | None,
    external_id: str | None,
    title: str,
    path: str | None = None,
) -> dict[str, Any]:
    """Best-effort metadata/content pull. Never raises.

    ``error`` is set when the underlying fetch could not run (a missing or
    failing CLI, an unreachable URL, a path that is gone) so a caller can
    surface the failure rather than treating empty output as a successful
    refresh.
    """

    result: dict[str, Any] = {"metadata": {}, "content": "", "title": title, "people": [], "error": None}
    try:
        if source == "file":
            _fetch_path(path or external_id or url, result)
        elif source == "github" and url:
            _fetch_github(url, result)
        elif source == "slack" and url:
            _fetch_slack(url, result)
        elif url and (source in ("url", "gdrive") or source == "web"):
            _fetch_url(url, result)
    except Exception as exc:  # noqa: BLE001
        log.info("fetch_source failed", source=source, url=url, error=str(exc))
        result["error"] = f"could not fetch {url or source}: {exc}"
    return result


def read_path(value: str | None) -> dict[str, Any]:
    """Read a path on demand without storing what it contains.

    The returned ``content`` is a live preview for a detail read, never written
    to the database: a path item is a reference, so the file can change without
    the stored item going stale.
    """
    result: dict[str, Any] = {
        "path": str(Path(value).expanduser()) if value else "",
        "exists": False,
        "kind": "",
        "size": None,
        "modified_at": None,
        "title": "",
        "content": "",
        "truncated": False,
        "error": None,
    }
    if not value:
        result["error"] = "no path to read"
        return result
    path = Path(value).expanduser()
    if not path.exists():
        result["error"] = f"{path} does not exist"
        return result

    try:
        stat = path.stat()
    except OSError as exc:
        result["error"] = f"Could not read {path}: {exc}"
        return result
    is_dir = path.is_dir()
    result.update(
        exists=True,
        kind="directory" if is_dir else "file",
        size=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
        title=path.name or str(path),
    )
    if is_dir:
        result["content"] = _directory_listing(path)
    else:
        result["content"], result["truncated"] = _file_preview(path)
    return result


def _fetch_path(value: str | None, result: dict[str, Any]) -> None:
    """Store a path's reference and stat metadata. Its content is read on demand."""
    preview = read_path(value)
    result["metadata"] = {key: preview[key] for key in ("path", "exists", "kind", "size", "modified_at")}
    if preview["title"] and not result["title"]:
        result["title"] = preview["title"]
    if preview["error"]:
        result["error"] = preview["error"]


def _directory_listing(path: Path) -> str:
    """A capped, one-entry-per-line live listing of a directory."""
    try:
        children = sorted(path.iterdir(), key=lambda child: (not child.is_dir(), child.name.lower()))
    except OSError as exc:
        return f"Could not list {path}: {exc}"
    lines = [f"{path}"]
    for child in children[:_PATH_LISTING_LIMIT]:
        suffix = "/" if child.is_dir() else ""
        lines.append(f"{child.name}{suffix}")
    if len(children) > _PATH_LISTING_LIMIT:
        lines.append(f"… and {len(children) - _PATH_LISTING_LIMIT} more")
    return "\n".join(lines)[:_PATH_CONTENT_LIMIT]


def _file_preview(path: Path) -> tuple[str, bool]:
    """A live text preview of a file, in full, and whether it was cut short.

    A text file is never capped: markdown and plain text are shown whole. A
    binary file gets a short note in place of its bytes.
    """
    try:
        with path.open("rb") as handle:
            head = handle.read(8192)
            if b"\x00" in head:
                return f"Binary file ({path.stat().st_size} bytes)", False
            data = head + handle.read()
    except OSError as exc:
        return f"Could not read {path}: {exc}", False
    return data.decode("utf-8", errors="replace"), False


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
