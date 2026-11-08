"""Read the 0-1 scores the review steps record in their report markers.

Every review step writes how well a pull request addresses its concern as a
``score`` between ``0`` and ``1`` in the report marker (see the skills' shared
conventions, Score (0-1)). This module reads those markers from the same
user-global store :mod:`agentic.review_store` serves and returns one row per
scored run, dated by the marker's ``reviewed_at`` (or the file's modification
time when the marker has none).

A report written before the score field existed is scored from its findings
state and verdict, following the same formula as the skills' own
``review_scores.py`` script, so history does not restart at the first scored
report. A report with no JSON marker at all is skipped: it predates the marker
format the app already relies on, so there is no run to date or score.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .config import settings
from .review_findings import _parse_findings_tolerantly
from .review_store import STEPS, iter_review_dirs, parse_view_cache
from .reviews import report_identity

MARKER_RE = re.compile(r"<!--\s*(\{.*?\})\s*-->", re.DOTALL)

#: The findings state file each step keeps its open findings in. A step without
#: an entry uses ``<step>.yaml``.
STATE_FILES: dict[str, str] = {
    "review-pr": "review.yaml",
    "validate-pr": "validate.yaml",
    "verify-pr": "verify.yaml",
}

#: The overall-light cap applied to a derived score, matching the skills'
#: Score (0-1) formula.
GREEN_CAP = 1.0
YELLOW_CAP = 0.75
RED_CAP = 0.25

_GREEN_VERDICTS = {"approved", "pass", "holds", "fast-track", "confirm", "right-thing", "informational"}
_YELLOW_VERDICTS = {"partial", "partially-right", "unproven", "decide", "investigate"}
_RED_VERDICTS = {
    "changes-requested",
    "rejected",
    "fail",
    "wrong-thing",
    "inconclusive",
    "breaks",
    "block",
    "hold",
}


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _marker(text: str) -> dict[str, Any] | None:
    """The last JSON marker in a report, or None."""
    found: dict[str, Any] | None = None
    for match in MARKER_RE.finditer(text):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            found = data
    return found


def _timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _cap_for_verdict(verdict: str) -> float:
    normalized = verdict.strip().lower()
    if normalized in _YELLOW_VERDICTS:
        return YELLOW_CAP
    if normalized in _RED_VERDICTS:
        return RED_CAP
    # A green verdict, or one this build does not know, caps at green. The raw
    # findings count below still lowers the score on its own.
    return GREEN_CAP


def _findings(path: Path) -> list[dict[str, Any]]:
    text = _read(path)
    if not text:
        return []
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return _parse_findings_tolerantly(text)
    if not isinstance(data, dict):
        return []
    return [entry for entry in (data.get("findings") or []) if isinstance(entry, dict)]


def _finding_counts(step: str, directory: Path) -> tuple[int, int, int]:
    """Return the step's (must, should, may) open-finding counts."""
    name = STATE_FILES.get(step, f"{step}.yaml")
    must = should = may = 0
    for finding in _findings(directory / name):
        status = str(finding.get("status", "open")).strip().lower()
        if step == "verify-pr":
            if status not in {"fails", "unverified", "conforms-static"}:
                continue
            severity = str(finding.get("severity", "")).strip().lower()
            if not severity:
                severity = "must" if status == "fails" else "should"
            if severity == "must":
                must += 1
            elif severity == "should":
                should += 1
            continue
        if status != "open":
            continue
        severity = str(finding.get("severity", "")).strip().lower()
        if severity == "must":
            must += 1
        elif severity == "should":
            should += 1
        elif severity == "may":
            may += 1
    return must, should, may


def _derived_score(step: str, directory: Path, verdict: str) -> float:
    """Score a report written before the marker carried a score."""
    must, should, may = _finding_counts(step, directory)
    raw = _clamp(1.0 - 0.5 * must - 0.2 * should - 0.05 * may)
    finding_cap = RED_CAP if must else YELLOW_CAP if (should or may) else GREEN_CAP
    cap = min(finding_cap, _cap_for_verdict(verdict))
    return round(min(raw, cap), 2)


def _report_files(directory: Path) -> list[tuple[Path, str, str]]:
    """The step reports in one PR directory as (path, step, commit).

    The stable ``<step>.report.md`` aliases are symlinks, so they are skipped;
    the per-run ``<step>.<sha>.md`` files are the history this module reads.
    """
    reports: list[tuple[Path, str, str]] = []
    for path in directory.glob("*.md"):
        if path.is_symlink() or not path.is_file():
            continue
        step, commit = report_identity(path.name)
        if step in STEPS:
            reports.append((path, step, commit or ""))
    return reports


def _author(directory: Path) -> str:
    view = parse_view_cache(_read(directory / "gh-pr-view.md"))
    return str(view.get("author", "") or "")


def collect_review_scores() -> list[dict[str, Any]]:
    """Every scored review run in the store, oldest first.

    A run is keyed by the report file, so a step reviewed twice at two commits
    contributes both runs. Filtering by repository, author, or step is the
    caller's job; the store is small enough to read whole.
    """
    runs: list[dict[str, Any]] = []
    for owner, name, number, directory in iter_review_dirs():
        repository = f"{owner}/{name}" if owner else name
        author = _author(directory)
        for path, step, commit in _report_files(directory):
            text = _read(path)
            marker = _marker(text)
            if marker is None:
                continue
            marker_step = str(marker.get("step", "")).strip()
            if marker_step and marker_step != step:
                continue
            verdict = str(marker.get("verdict", "")).strip()
            reviewed_at = _timestamp(marker.get("reviewed_at") or marker.get("generated_at"))
            if reviewed_at is None:
                try:
                    reviewed_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
                except OSError:
                    continue
            score: float | None = None
            raw_score = marker.get("score")
            if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool):
                score = _clamp(float(raw_score))
            source = "marker"
            if score is None:
                source = "derived"
                score = _derived_score(step, directory, verdict)
            runs.append(
                {
                    "repository": repository,
                    "owner": owner,
                    "name": name,
                    "number": number,
                    "author": author,
                    "step": step,
                    "sha": str(marker.get("sha", commit) or commit),
                    "verdict": verdict,
                    "score": round(score, 2),
                    "source": source,
                    "reviewed_at": reviewed_at,
                }
            )
    runs.sort(key=lambda run: (run["reviewed_at"], run["repository"], run["number"], run["step"]))
    return runs


def store_root() -> str | None:
    """The store path, or None when it does not exist yet."""
    root = settings.sdlc_dir.expanduser()
    return str(root) if root.is_dir() else None
