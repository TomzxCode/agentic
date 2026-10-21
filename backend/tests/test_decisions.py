"""Colleague-decisions page: parsing the notes reports and the /api/decisions payload."""

from pathlib import Path

from fastapi.testclient import TestClient

from agentic.config import settings
from agentic.decisions_store import build_payload, discover_reports, parse_report
from agentic.main import app

REPORT = """# Colleague decisions — 2026-10-02

Searched 3 colleagues over 2026-10-02.

## Alice Smith
**Headline:** Adopt the shared queue
- **Decided:** Move the queue to Redis. [thread](https://example.slack.com/archives/C1/p1)
  - **Supported by:** Bob Jones, Carol Diaz
  - **Opposed by:** Dan Ng
- **Deferred:** The migration plan (next sprint). https://example.slack.com/archives/C1/p2
- **Open:** Do we need a fallback? https://example.slack.com/archives/C1/p3

## Bob Jones
- **Committed:** Bob Jones to write the runbook. https://example.slack.com/archives/C1/p4

## Not heard from (no decisions)
- Carol Diaz, Erin Fox

## Cross-cutting
Two people agreed on the queue move.
"""


def _write(root: Path, day: str, text: str = REPORT, name: str | None = None) -> Path:
    """Write a report in the skill's layout: {root}/decisions/YYYY/MM/DD.md."""
    year, month, date = day.split("-")
    directory = root / "decisions" / year / month
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (name or f"{date}.md")
    path.write_text(text, encoding="utf-8")
    return path


def test_parse_report_reads_every_section(tmp_path):
    report = parse_report(_write(tmp_path, "2026-10-02"), REPORT)

    assert report.day == "2026-10-02"
    assert report.headline == {"Alice Smith": "Adopt the shared queue"}
    assert [decision.bucket for decision in report.decisions] == ["Decided", "Deferred", "Open", "Committed"]
    assert [decision.author for decision in report.decisions] == [
        "Alice Smith",
        "Alice Smith",
        "Alice Smith",
        "Bob Jones",
    ]

    decided = report.decisions[0]
    # The permalink is pulled out of the decision's text, in either form.
    assert decided.text == "Move the queue to Redis."
    assert decided.permalink == "https://example.slack.com/archives/C1/p1"
    assert decided.supported_by == ["Bob Jones", "Carol Diaz"]
    assert decided.opposed_by == ["Dan Ng"]
    assert report.decisions[1].permalink == "https://example.slack.com/archives/C1/p2"

    # A name under "Not heard from" is split on commas, with the heading's
    # parenthetical dropped, not treated as a person section.
    assert report.not_heard == ["Carol Diaz", "Erin Fox"]
    assert report.cross_cutting == "Two people agreed on the queue move."


def test_parse_report_drops_the_author_from_their_own_support_list(tmp_path):
    text = """## Alice Smith
- **Decided:** Ship it.
  - **Supported by:** Alice Smith, Bob Jones
"""
    report = parse_report(_write(tmp_path, "2026-10-02"), text)
    assert report.decisions[0].supported_by == ["Bob Jones"]


def test_discover_reports_reads_both_layouts_and_skips_dotfiles(tmp_path):
    _write(tmp_path, "2026-10-03")
    _write(tmp_path, "2026-10-02")
    _write(tmp_path, "2026-10-01")
    ad_hoc = tmp_path / "2026-10-04.colleague-decisions.md"
    ad_hoc.write_text(REPORT, encoding="utf-8")
    (tmp_path / ".tmp.md").write_text(REPORT, encoding="utf-8")

    reports = discover_reports(tmp_path)
    assert [report.day for report in reports] == ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]
    assert str(ad_hoc) in [report.path for report in reports]


def test_build_payload_aggregates_and_dedupes(tmp_path):
    _write(tmp_path, "2026-10-01")
    # An ad-hoc report for the same day repeats the same decisions: each is kept
    # once.
    (tmp_path / "2026-10-01.colleague-decisions.md").write_text(REPORT, encoding="utf-8")

    payload = build_payload(discover_reports(tmp_path))

    assert payload["reports"] == 2
    assert payload["counts"] == {"decisions": 4, "people": 2, "supporters": 2, "opponents": 1}
    assert payload["range"] == {"start": "2026-10-01", "end": "2026-10-01"}
    # Newest first, and within a day the author and bucket order reverse, as the
    # script's page does.
    assert [decision.author for decision in payload["decisions"]] == [
        "Bob Jones",
        "Alice Smith",
        "Alice Smith",
        "Alice Smith",
    ]
    assert [decision.bucket for decision in payload["decisions"]] == ["Committed", "Open", "Deferred", "Decided"]
    # Carol supported a decision, so she was heard; only Erin remains.
    assert payload["not_heard"] == ["Erin Fox"]
    assert payload["headlines"] == {"Alice Smith": "Adopt the shared queue"}
    # Both reports carry the same note, and the script keeps one entry per report,
    # so the payload does too.
    assert payload["cross_cutting"] == ["Two people agreed on the queue move."] * 2


def test_build_payload_bounds_the_days(tmp_path):
    _write(tmp_path, "2026-10-01")
    reports = discover_reports(tmp_path)

    assert build_payload(reports, since="2026-10-02")["decisions"] == []
    assert build_payload(reports, until="2026-10-02")["decisions"]
    assert build_payload(reports)["decisions"]


def test_list_decisions_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "notes_dir", tmp_path)
    _write(tmp_path, "2026-10-02")

    with TestClient(app) as client:
        payload = client.get("/api/decisions").json()

    assert payload["root"] == str(tmp_path)
    assert payload["generated_at"]
    assert payload["reports"] == 1
    assert payload["counts"]["decisions"] == 4
    decided = next(decision for decision in payload["decisions"] if decision["bucket"] == "Decided")
    assert decided["text"] == "Move the queue to Redis."
    assert decided["permalink"] == "https://example.slack.com/archives/C1/p1"
    assert decided["supported_by"] == ["Bob Jones", "Carol Diaz"]


def test_list_decisions_reports_a_missing_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "notes_dir", tmp_path / "nope")

    with TestClient(app) as client:
        payload = client.get("/api/decisions").json()

    assert payload["root"] is None
    assert payload["reports"] == 0
    assert payload["decisions"] == []
    assert payload["range"] is None
