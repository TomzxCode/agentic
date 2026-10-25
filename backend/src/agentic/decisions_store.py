"""Read the colleague-decisions reports the extract-colleague-decisions skill writes.

The skill writes one Markdown report per day under the user's notes tree::

    {notes_dir}/decisions/{YYYY}/{MM}/{DD}.md

or, for an ad-hoc run, any ``*.colleague-decisions.md`` file. Each report names
the people it covered, the decision each one made (Decided, Deferred, Open, or
Committed), who supported or opposed it, and a Slack permalink. This module
parses those reports into the rows the Decisions page shows.

It mirrors ``scripts/colleague_decisions_page.py`` in the agents repository: the
same file layout, the same labels, and the same support and opposition rules, so
the page and the script never disagree about what a report says.

The store is read-only and never imports FastAPI, so a router maps its result to
a response.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

#: The decision buckets a report can name, in display order.
DECISION_BUCKETS: tuple[str, ...] = ("Decided", "Deferred", "Open", "Committed")

_DATE_RE = re.compile(r"(\d{4})[/-](\d{2})[/-](\d{2})")
_DECISION_RE = re.compile(r"^\s*[-*]\s+\*\*(Decided|Deferred|Open|Committed):\*\*\s*(.*)$")
_SUPPORT_RE = re.compile(r"^\s*[-*]\s+\*\*Supported by:\*\*\s*(.*)$")
_OPPOSE_RE = re.compile(r"^\s*[-*]\s+\*\*Opposed by:\*\*\s*(.*)$")
_HEADLINE_RE = re.compile(r"^\*\*Headline:\*\*\s*(.*)$")
_SECTION_RE = re.compile(r"^##\s+(.*)$")
_URL_RE = re.compile(r"https?://[^\s)>\]]+")
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^)]+)\)")
_NAME_SPLIT_RE = re.compile(r"\s*(?:,|;|/|\band\b)\s*", re.IGNORECASE)
_NOT_HEARD_RE = re.compile(r"^not heard", re.IGNORECASE)
_CROSS_RE = re.compile(r"^cross-cutting", re.IGNORECASE)


@dataclass
class Decision:
    """One decision a colleague made, as its report records it."""

    date: str
    author: str
    bucket: str
    text: str
    permalink: str = ""
    supported_by: list[str] = field(default_factory=list)
    opposed_by: list[str] = field(default_factory=list)
    source: str = ""


@dataclass
class Report:
    """One decisions report: its day, its people, and its shared sections."""

    day: str
    path: str
    decisions: list[Decision]
    headline: dict[str, str]
    not_heard: list[str]
    cross_cutting: str


def _clean_name(raw: str) -> str:
    return raw.strip().lstrip("@").strip()


def _split_names(raw: str) -> list[str]:
    raw = re.sub(r"\([^)]*\)", "", raw)
    names: list[str] = []
    for part in _NAME_SPLIT_RE.split(raw):
        name = _clean_name(part)
        if name:
            names.append(name)
    return names


def _extract_url(text: str) -> tuple[str, str]:
    """Split the last link out of *text*, returning the text without it and the URL."""
    links = _MD_LINK_RE.findall(text)
    if links:
        url = links[-1].rstrip(".,;")
        return _MD_LINK_RE.sub("", text).strip().rstrip("·-").strip(), url
    urls = _URL_RE.findall(text)
    if not urls:
        return text.strip(), ""
    url = urls[-1].rstrip(".,;")
    cleaned = text.replace(url, "")
    return cleaned.strip().rstrip("·-").strip(), url


def parse_report(path: Path, text: str) -> Report:
    """Parse one report's Markdown into its decisions and shared sections."""
    match = _DATE_RE.search(str(path))
    day = f"{match.group(1)}-{match.group(2)}-{match.group(3)}" if match else path.stem

    decisions: list[Decision] = []
    headline: dict[str, str] = {}
    not_heard: list[str] = []
    cross_lines: list[str] = []
    person: str | None = None
    special: str | None = None
    current: Decision | None = None

    for line in text.splitlines():
        section = _SECTION_RE.match(line)
        if section:
            person = None
            special = None
            name = section.group(1).strip()
            if _NOT_HEARD_RE.match(name):
                special = "not_heard"
            elif _CROSS_RE.match(name):
                special = "cross"
            else:
                person = _clean_name(name)
            current = None
            continue

        if special == "not_heard":
            stripped = line.strip()
            if stripped.startswith(("-", "*")):
                not_heard.extend(_split_names(stripped.lstrip("-* ").strip()))
            continue
        if special == "cross":
            if line.strip():
                cross_lines.append(line.rstrip())
            continue

        if person is None:
            continue

        if current is not None:
            support = _SUPPORT_RE.match(line)
            oppose = _OPPOSE_RE.match(line)
            if support or oppose:
                target = current.supported_by if support else current.opposed_by
                match = support or oppose
                assert match is not None
                for name in _split_names(match.group(1)):
                    if name.casefold() != person.casefold() and name not in target:
                        target.append(name)
                continue
            if not current.permalink:
                _, url = _extract_url(line)
                if url:
                    current.permalink = url
                    continue

        head = _HEADLINE_RE.match(line)
        if head and current is None:
            headline[person] = head.group(1).strip()
            continue

        decision = _DECISION_RE.match(line)
        if decision:
            body, url = _extract_url(decision.group(2))
            current = Decision(
                date=day,
                author=person,
                bucket=decision.group(1),
                text=body,
                permalink=url,
                source=str(path),
            )
            decisions.append(current)
            continue

        # An indented continuation belongs to the decision above it; a new
        # section or paragraph does not, and ends the current decision.
        if current is not None and line.strip() and line.startswith((" ", "\t")):
            continue

    return Report(
        day=day,
        path=str(path),
        decisions=decisions,
        headline=headline,
        not_heard=not_heard,
        cross_cutting="\n".join(cross_lines).strip(),
    )


def discover_reports(root: Path) -> list[Report]:
    """Every decisions report under *root*, oldest first.

    Dotfiles (an editor's temporary file) are skipped because they are not
    reports. A file that cannot be read is skipped rather than failing the page.
    """
    seen: set[Path] = set()
    paths: list[Path] = []
    for pattern in ("**/decisions/*/*/*.md", "**/*.colleague-decisions.md"):
        for path in root.glob(pattern):
            if path.name.startswith(".") or path in seen:
                continue
            seen.add(path)
            paths.append(path)

    reports: list[Report] = []
    for path in sorted(paths):
        try:
            reports.append(parse_report(path, path.read_text(encoding="utf-8")))
        except OSError:
            continue
    reports.sort(key=lambda report: (report.day, report.path))
    return reports


def build_payload(reports: list[Report], since: str | None = None, until: str | None = None) -> dict:
    """Aggregate *reports* into the rows, counts, and shared sections the page shows.

    ``since`` and ``until`` bound the days included, as ``YYYY-MM-DD`` strings.
    A decision repeated across reports is kept once.
    """
    selected = [
        report for report in reports if not (since and report.day < since) and not (until and report.day > until)
    ]

    decisions: list[Decision] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for report in selected:
        for decision in report.decisions:
            key = (
                decision.date,
                decision.author,
                decision.bucket,
                decision.text,
                decision.permalink,
            )
            if key in seen:
                continue
            seen.add(key)
            decisions.append(decision)

    decisions.sort(key=lambda d: (d.date, d.author, DECISION_BUCKETS.index(d.bucket)), reverse=True)

    heard = (
        {d.author.casefold() for d in decisions}
        | {name.casefold() for d in decisions for name in d.supported_by}
        | {name.casefold() for d in decisions for name in d.opposed_by}
    )
    not_heard = sorted(
        {name for report in selected for name in report.not_heard if name.casefold() not in heard},
        key=str.casefold,
    )
    headlines = {name: headline for report in selected for name, headline in report.headline.items() if headline}
    cross = [report.cross_cutting for report in selected if report.cross_cutting]

    days = sorted({d.date for d in decisions})
    return {
        "reports": len(reports),
        "counts": {
            "decisions": len(decisions),
            "people": len({d.author for d in decisions}),
            "supporters": len({name for d in decisions for name in d.supported_by}),
            "opponents": len({name for d in decisions for name in d.opposed_by}),
        },
        "range": {"start": days[0], "end": days[-1]} if days else None,
        "decisions": decisions,
        "headlines": headlines,
        "not_heard": not_heard,
        "cross_cutting": cross,
    }
