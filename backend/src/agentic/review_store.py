"""Read the user-global SDLC store as a pull-request review queue.

The review skills (``review-pr-full`` and its ``review-*`` chain) leave their
Markdown reports, each opening with a JSON marker comment, under::

    $HOME/.sdlc/{owner}/{repository}/pull-requests/{number}/

This module turns that store into the rows the ``/reviews`` view shows: one row
per pull request with the state of every review step, mirroring what the
``review_requested_prs.py`` orchestrator prints. The script discovers PRs live
from GitHub; the app reads the same store the skills wrote, so the set of rows
is whatever the store holds.

A pull request's own fields (its title, state, author, and creation time) come
from ghx, which is the same source the rest of the app reads GitHub through; the
store's ``gh-pr-view.md`` cache stands in only when ghx cannot answer. A field
that would need a read nothing here makes (the diff size, the review approvers,
the open-PR stack a PR blocks) is left out rather than guessed. The commit a
report reviewed stands in for the PR's head, so a step is stale when its report
does not cover the newest reviewed commit.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from .config import settings
from .reviews import report_identity

log = structlog.get_logger(__name__)

#: How long a ghx lookup of a pull request's GitHub fields is reused, so a page
#: reload does not shell out again. A Refresh (``?refresh=true``) bypasses it.
GITHUB_METADATA_TTL = 300
#: A lookup that failed (ghx missing, offline) is retried after this long rather
#: than on every request.
GITHUB_METADATA_FAILED_TTL = 60

#: (owner, repo, number) -> (monotonic fetch time, ghx metadata or None).
_metadata_cache: dict[tuple[str, str, int], tuple[float, dict[str, Any] | None]] = {}

#: The review steps, in the order the script weighs them: the two parallel steps
#: first, then the chain (coverage advisory, then validate -> verify -> review).
STEPS: tuple[str, ...] = (
    "assess-pr-risk",
    "summarize-behavior-changes",
    "analyze-test-coverage",
    "validate-pr",
    "verify-pr",
    "review-pr",
)

#: The assess-pr-risk routes that block a merge, and the ones that only ask the
#: reviewer to look closer before deciding.
BLOCKING_ROUTES = {"block", "hold"}
SLOW_ROUTES = {"decide", "investigate"}

MARKER_RE = re.compile(r"<!--\s*(\{.*?\})\s*-->", re.DOTALL)
RISK_RE = re.compile(r"Risk:\s*(Low|Medium|High)\b", re.IGNORECASE)
CONFIDENCE_RE = re.compile(r"Confidence:\s*(Low|Medium|High)\b", re.IGNORECASE)

#: The ``gh pr view`` cache the skills leave as ``gh-pr-view.md``: a title line, a
#: "STATE • opened by AUTHOR • N comment(s)" line, then labelled fields.
VIEW_TITLE_RE = re.compile(r"^#(?P<number>\d+)\s+(?P<title>.*)$")
VIEW_STATE_RE = re.compile(r"^(?P<state>[A-Z_]+)\s+•\s+opened by (?P<author>\S+)", re.MULTILINE)
VIEW_BRANCH_RE = re.compile(r"^Branch:\s+(?P<head>\S+)\s+→\s+(?P<base>\S+)", re.MULTILINE)
VIEW_LABELS_RE = re.compile(r"^Labels:\s+(?P<labels>.+)$", re.MULTILINE)
VIEW_CREATED_RE = re.compile(r"^Created:\s+(?P<created>.+)$", re.MULTILINE)
VIEW_URL_RE = re.compile(r"^URL:\s+(?P<url>\S+)", re.MULTILINE)
VIEW_COMMENT_RE = re.compile(r"──\s*Comment \d+ by (?P<by>\S+) \((?P<when>[^)]+)\)")

VIEW_TIME_FORMAT = "%Y-%m-%d %H:%M"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _parse_marker(text: str) -> dict[str, Any] | None:
    """Return the last review-step marker in *text*, or None.

    The marker is a JSON comment ``<!-- {"step": ..., "sha": ..., ...} -->``; a
    file's most recent marker wins, matching the script's scan.
    """
    found: dict[str, Any] | None = None
    for match in MARKER_RE.finditer(text):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("step") in STEPS:
            found = data
    return found


def _step_for_file(name: str) -> tuple[str | None, str | None]:
    """The step and reviewed commit a report file belongs to, if any.

    ``review-pr.abc1234.md`` yields the step and its short commit. The stable
    ``validate-pr.report.md`` alias carries no commit; it is credited to its step
    so the verdict is still read, without a reviewed commit.
    """
    skill, commit = report_identity(name)
    if skill in STEPS:
        return skill, commit
    stem = Path(name).stem
    base = stem[: -len(".report")] if stem.endswith(".report") else stem
    if base in STEPS:
        return base, None
    return None, None


def _candidate_reports(directory: Path) -> dict[str, list[tuple[Path, str | None]]]:
    """The per-step report files under *directory*, skipping aliases and dot dirs."""
    candidates: dict[str, list[tuple[Path, str | None]]] = {}
    for path in directory.rglob("*.md"):
        # The stable ``<step>.report.md`` names are usually symlinks to the
        # per-run files; a symlink would only duplicate its target.
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(directory)
        if any(part.startswith(".") for part in rel.parts):
            continue
        step, commit = _step_for_file(rel.as_posix())
        if step is None:
            continue
        candidates.setdefault(step, []).append((path, commit))
    return candidates


def _step_state(directory: Path) -> tuple[dict[str, dict[str, Any]], str]:
    """Read every step's newest report under *directory*.

    Returns the per-step state (keyed by step) and the newest reviewed commit
    across the steps, which stands in for the PR's head. A step whose newest
    report carries no commit (a ``.report.md`` alias) still reports its verdict.
    """
    steps: dict[str, dict[str, Any]] = {}
    reference = ""
    reference_mtime = float("-inf")
    for step, entries in _candidate_reports(directory).items():
        with_commit = [entry for entry in entries if entry[1]]
        pool = with_commit or entries
        path, commit = max(pool, key=lambda entry: entry[0].stat().st_mtime)
        modified = path.stat().st_mtime
        text = _read_text(path)
        marker = _parse_marker(text) or {}
        state: dict[str, Any] = {
            "step": step,
            "commit": commit or "",
            "verdict": str(marker.get("verdict", "") or ""),
            "risk": "",
            "confidence": "",
            "report": path.relative_to(directory).as_posix(),
            "modified_at": datetime.fromtimestamp(modified),
        }
        if step == "assess-pr-risk":
            state["risk"], state["confidence"] = _assess_fields(text, marker)
        steps[step] = state
        if commit and modified >= reference_mtime:
            reference = commit
            reference_mtime = modified
    return steps, reference


def _assess_fields(text: str, marker: dict[str, Any]) -> tuple[str, str]:
    """The risk and confidence of an assess-pr-risk report.

    Prefers the marker's own keys and falls back to scraping the report body
    line, the same order the script uses.
    """
    risk = str(marker.get("risk", "") or "").lower()
    confidence = str(marker.get("confidence", "") or "").lower()
    if risk not in ("low", "medium", "high"):
        match = RISK_RE.search(text)
        risk = match.group(1).lower() if match else ""
    if confidence not in ("low", "medium", "high"):
        match = CONFIDENCE_RE.search(text)
        confidence = match.group(1).lower() if match else ""
    return risk, confidence


def determine_stale_steps(steps: dict[str, dict[str, Any]], reference: str) -> list[str]:
    """The review steps that do not cover the newest reviewed commit.

    Mirrors the script's staleness rule against the newest reviewed commit
    instead of the PR's head: the two parallel steps are stale independently of
    the chain, and a chain step that does not cover the commit makes every step
    after it stale too.
    """

    def stale(step: str) -> bool:
        return steps.get(step, {}).get("commit") != reference

    result: list[str] = []
    if stale("assess-pr-risk"):
        result.append("assess-pr-risk")
    if stale("summarize-behavior-changes"):
        result.append("summarize-behavior-changes")
    if stale("analyze-test-coverage"):
        result.append("analyze-test-coverage")
    if stale("validate-pr"):
        return result + ["validate-pr", "verify-pr", "review-pr"]
    if stale("verify-pr"):
        return result + ["verify-pr", "review-pr"]
    if stale("review-pr"):
        result.append("review-pr")
    return result


def readiness_signal(steps: dict[str, dict[str, Any]], stale_steps: list[str], draft: bool) -> str:
    """Classify a PR's merge readiness from its review-step state.

    ``red`` when a chain verdict fails or the assess step routes to a blocking
    route; ``green`` when nothing is stale, the review passed, coverage did not
    fail, and the assess route is not one asking for a closer look; ``yellow``
    otherwise.
    """

    def verdict(step: str) -> str:
        return steps.get(step, {}).get("verdict", "")

    if any(verdict(step) == "fail" for step in ("validate-pr", "verify-pr", "review-pr")):
        return "red"
    if verdict("assess-pr-risk") in BLOCKING_ROUTES:
        return "red"
    if (
        not draft
        and not stale_steps
        and verdict("review-pr") == "pass"
        and verdict("analyze-test-coverage") != "fail"
        and verdict("assess-pr-risk") not in SLOW_ROUTES
    ):
        return "green"
    return "yellow"


def parse_view_cache(text: str) -> dict[str, Any]:
    """The fields named in a ``gh pr view`` cache (``gh-pr-view.md``).

    The skills write that file with the PR's title, state, author, branch,
    labels, creation time, URL, and its comment threads, so the store alone can
    fill the author, age, and last-comment columns. Missing lines are skipped.
    """
    parsed: dict[str, Any] = {}
    lines = text.splitlines()
    title = VIEW_TITLE_RE.match(lines[0]) if lines else None
    if title:
        parsed["title"] = title.group("title").strip()
    state = VIEW_STATE_RE.search(text)
    if state:
        parsed["state"] = state.group("state")
        parsed["author"] = state.group("author")
    branch = VIEW_BRANCH_RE.search(text)
    if branch:
        parsed["head_branch"] = branch.group("head")
        parsed["base_branch"] = branch.group("base")
    labels = VIEW_LABELS_RE.search(text)
    if labels:
        parsed["labels"] = [label.strip() for label in labels.group("labels").split(",") if label.strip()]
    created = VIEW_CREATED_RE.search(text)
    if created:
        parsed["created_at"] = _parse_view_time(created.group("created"))
    url = VIEW_URL_RE.search(text)
    if url:
        parsed["url"] = url.group("url")
    comments = VIEW_COMMENT_RE.findall(text)
    if comments:
        # gh prints comment times in local time; the newest one is the last.
        newest = max(comments, key=lambda entry: entry[1])
        parsed["last_comment_by"] = newest[0]
        parsed["last_comment_at"] = _parse_view_time(newest[1])
    return parsed


def _parse_view_time(value: str) -> str | None:
    """A ``gh pr view`` local time (``YYYY-MM-DD HH:MM``) as an ISO string."""
    try:
        return datetime.strptime(value.strip(), VIEW_TIME_FORMAT).astimezone().isoformat()
    except ValueError:
        return None


def iter_review_dirs() -> list[tuple[str, str, int, Path]]:
    """Every PR review directory under the store.

    Returns ``(owner, name, number, directory)`` for each. Both layouts the store
    accepts are found: ``{owner}/{repo}/pull-requests/{n}`` and the bare
    ``{repo}/pull-requests/{n}``. The owner is "" for a bare store key.
    """
    root = settings.sdlc_dir.expanduser()
    if not root.is_dir():
        return []
    found: dict[Path, tuple[str, str, int, Path]] = {}
    for directory in root.glob("*/*/pull-requests/*"):
        if directory.is_dir() and directory.name.isdigit() and directory.resolve() not in found:
            owner, name = directory.parent.parent.parent.name, directory.parent.parent.name
            found[directory.resolve()] = (owner, name, int(directory.name), directory)
    for directory in root.glob("*/pull-requests/*"):
        if directory.is_dir() and directory.name.isdigit() and directory.resolve() not in found:
            name = directory.parent.parent.name
            found[directory.resolve()] = ("", name, int(directory.name), directory)
    return list(found.values())


def _pull_url(owner: str, name: str, number: int) -> str:
    repository = f"{owner}/{name}" if owner else name
    return f"https://github.com/{repository}/pull/{number}"


def collect_review_prs() -> list[dict[str, Any]]:
    """Every PR in the store with the state of its review steps."""
    prs: list[dict[str, Any]] = []
    for owner, name, number, directory in iter_review_dirs():
        view = parse_view_cache(_read_text(directory / "gh-pr-view.md"))
        steps, reference = _step_state(directory)
        stale_steps = determine_stale_steps(steps, reference)
        for state in steps.values():
            # A step is stale when its own report does not cover the newest
            # reviewed commit; stale_steps also carries the chain steps a
            # staleness cuts off, which may be current themselves.
            state["stale"] = state["commit"] != reference
        draft = bool(view.get("draft", False))
        prs.append(
            {
                "owner": owner,
                "name": name,
                "repository": f"{owner}/{name}" if owner else name,
                "number": number,
                "title": view.get("title", ""),
                "url": view.get("url", "") or _pull_url(owner, name, number),
                "author": view.get("author", ""),
                "state": view.get("state", ""),
                "draft": draft,
                "head_branch": view.get("head_branch", ""),
                "base_branch": view.get("base_branch", ""),
                "labels": view.get("labels", []),
                "created_at": view.get("created_at"),
                "last_comment_at": view.get("last_comment_at"),
                "last_comment_by": view.get("last_comment_by", ""),
                "head_commit": reference,
                "steps": steps,
                "stale_steps": stale_steps,
                "reviewed_steps": len(steps),
                "readiness": readiness_signal(steps, stale_steps, draft),
                "status": "ready" if not stale_steps else "needs-review",
                "store_dir": str(directory),
            }
        )
    prs.sort(key=lambda pr: (pr["repository"].lower(), -pr["number"]))
    return prs
