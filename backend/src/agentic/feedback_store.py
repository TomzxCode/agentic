"""Read and write the reviewer-feedback analysis files the skills leave behind.

``handle-pr-reviewer-feedback`` analyzes the comments left on the pull requests
you authored and writes one Markdown analysis file per comment under::

    $HOME/.sdlc/{owner}/{repository}/pull-requests/{number}/feedback/{id}.md

Each file opens with YAML frontmatter (provenance, an advisory recommendation,
and the decision keys) followed by a body of named sections. This module parses
those files into the rows the PR-feedback view shows, and writes a decision back
into a file's frontmatter using the keys that skill and its executor consume.

Recording a decision writes ``decision`` and ``decided_at`` but not
``executed_at``, leaving the item in the "decided but not run" state so
``handle-pr-reviewer-feedback`` can carry it out later. Changing or resetting a
decision clears any stale ``executed_at``, so the new decision is run too.

The store is user-global like the PR review reports: outside any repository, not
governed by ``SDLC_DIR``, and never committed. This module only reads and writes
the files; it does not import FastAPI, so a router maps its errors to responses.
"""

from __future__ import annotations

import datetime as dt
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

#: The order the sections are shown in, the "Comment" first. A section the file
#: carries that is not listed here is still shown, after these.
FEEDBACK_SECTIONS: tuple[str, ...] = (
    "Comment",
    "Analysis",
    "Recommended action",
    "Suggested reply",
    "Suggested change",
)

#: The glob that finds the analysis files under the store root.
FEEDBACK_GLOB = "**/pull-requests/*/feedback/*.md"

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


@dataclass
class FeedbackItem:
    """One reviewer-feedback analysis file: its frontmatter, title, and sections."""

    feedback_id: str
    kind: str
    repo: str
    pr: str
    author: str
    created_at: str
    head_commit: str
    analyzed_at: str
    recommendation: str
    confidence: str
    session_link: str
    decision: str | None
    decided_at: str | None
    executed_at: str | None
    title: str
    path: str
    sections: dict[str, str] = field(default_factory=dict)

    @property
    def status(self) -> str:
        """The decision, or ``pending`` when none is recorded yet."""
        return self.decision or "pending"

    @property
    def run_state(self) -> str:
        """Execution state: ``executed``, ``awaiting``, or ``none``."""
        if self.executed_at:
            return "executed"
        if self.decision:
            return "awaiting"
        return "none"


def _split_sections(body: str) -> tuple[str, dict[str, str]]:
    """Split a file body into its ``#`` title and its ``##`` sections."""
    title = ""
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in body.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return title, sections


def _as_str(value: object) -> str:
    """A frontmatter value as a string, with a timestamp normalized to ISO-8601.

    YAML parses an unquoted timestamp (``decided_at``, ``executed_at``) into a
    datetime, which would otherwise render as ``2026-10-19 02:34:23+00:00``. The
    store's convention is ISO-8601 UTC, so a datetime is rendered that way; a
    naive one is assumed UTC rather than the machine's zone.
    """
    if isinstance(value, dt.datetime):
        moment = value if value.tzinfo is not None else value.replace(tzinfo=dt.UTC)
        return moment.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)


def parse_feedback(path: Path) -> FeedbackItem | None:
    """Read one analysis file, or None when it has no usable frontmatter."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    title, sections = _split_sections(match.group(2))
    return FeedbackItem(
        feedback_id=_as_str(data.get("feedback_id") or path.stem),
        kind=_as_str(data.get("kind") or ""),
        repo=_as_str(data.get("repo") or ""),
        pr=_as_str(data.get("pr") or ""),
        author=_as_str(data.get("author") or ""),
        created_at=_as_str(data.get("created_at") or ""),
        head_commit=_as_str(data.get("head_commit") or ""),
        analyzed_at=_as_str(data.get("analyzed_at") or ""),
        recommendation=_as_str(data.get("recommendation") or ""),
        confidence=_as_str(data.get("confidence") or ""),
        session_link=_as_str(data.get("session_link") or ""),
        decision=(_as_str(data["decision"]) if data.get("decision") else None),
        decided_at=(_as_str(data["decided_at"]) if data.get("decided_at") else None),
        executed_at=(_as_str(data["executed_at"]) if data.get("executed_at") else None),
        title=title or path.stem,
        path=str(path),
        sections=sections,
    )


def discover_feedback(root: Path) -> list[FeedbackItem]:
    """Every analysis file under *root*, undecided first, then by PR and age.

    The order matches what the triage view shows at rest: the items still
    awaiting a decision lead, grouped by repository and pull request, oldest
    comment first within a PR. A dotfile (an editor's temporary file) is skipped
    because it is not an analysis file.
    """
    items: list[FeedbackItem] = []
    if not root.is_dir():
        return items
    for path in sorted(root.glob(FEEDBACK_GLOB)):
        if path.name.startswith("."):
            continue
        item = parse_feedback(path)
        if item is not None:
            items.append(item)

    def sort_key(it: FeedbackItem) -> tuple:
        return (
            0 if it.decision is None else 1,
            it.repo,
            int(it.pr) if it.pr.isdigit() else 0,
            it.created_at,
            it.feedback_id,
        )

    items.sort(key=sort_key)
    return items


def find_feedback(root: Path, feedback_id: str) -> Path | None:
    """The analysis file whose stem is *feedback_id*, or None."""
    for path in sorted(root.glob(FEEDBACK_GLOB)):
        if path.name.startswith("."):
            continue
        if path.stem == feedback_id:
            return path
    return None


def write_decision(path: Path, decision: str | None) -> None:
    """Write (or clear) the ``decision`` keys in the file's frontmatter.

    A new decision, or a reset to None, has not been carried out yet, so a stale
    ``executed_at`` is dropped and the item is picked up by the executor again.
    Re-recording the same decision leaves an existing execution marker alone, so
    a repeat click does not re-queue work that already ran.

    Raises ``ValueError`` when the file has no frontmatter to write into.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}") from exc
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("file has no frontmatter")
    frontmatter, rest = match.group(1), match.group(2)

    existing = ""
    for line in frontmatter.splitlines():
        found = re.match(r"^decision\s*:\s*(.*)$", line)
        if found:
            existing = found.group(1).strip().strip("\"'")
    changed = decision != (existing or None)

    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: list[str] = []
    seen_decision = False
    seen_decided = False
    for line in frontmatter.splitlines():
        if re.match(r"^decision\s*:", line):
            seen_decision = True
            if decision:
                out.append(f"decision: {decision}")
        elif re.match(r"^decided_at\s*:", line):
            seen_decided = True
            if decision:
                out.append(line if not changed else f"decided_at: {now}")
        elif re.match(r"^executed_at\s*:", line):
            if decision and not changed:
                out.append(line)
        else:
            out.append(line)
    if decision:
        if not seen_decision:
            out.append(f"decision: {decision}")
        if not seen_decided:
            out.append(f"decided_at: {now}")

    new_text = "---\n" + "\n".join(out) + "\n---\n" + rest
    # Write beside the file and replace, so a crash cannot leave it truncated.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as handle:
        handle.write(new_text)
        tmp = Path(handle.name)
    tmp.replace(path)
