"""The must/should/may findings the review skills record per pull request."""

import pytest
from fastapi.testclient import TestClient

from agentic.config import settings
from agentic.main import app
from agentic.review_findings import collect_findings


def _write_state(root, name, findings):
    directory = root / "TomzxCode" / "agentic" / "pull-requests" / "42"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(_yaml(findings))
    return directory


def _yaml(findings):
    """Render a findings-state file the way the skills write it."""
    lines = ["pr: 42", "updated_at: 2026-01-12T06:00:00Z", "findings:"]
    for finding in findings:
        lines.append(f"  - title: {finding['title']}")
        lines.append(f"    description: {finding.get('description', '')}")
        lines.append(f"    severity: {finding['severity']}")
        lines.append(f"    status: {finding.get('status', 'open')}")
        lines.append(f"    first_seen_sha: {finding.get('sha', 'abc1234')}")
    return "\n".join(lines) + "\n"


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)


def test_collect_findings_orders_by_severity_across_state_files(tmp_path):
    _write_state(
        tmp_path,
        "review.yaml",
        [
            {"title": "Fix the thing", "severity": "must", "description": "It is broken."},
            {"title": "Tidy the helper", "severity": "may"},
        ],
    )
    _write_state(tmp_path, "validate.yaml", [{"title": "Link an issue", "severity": "should"}])

    findings = collect_findings("TomzxCode", "agentic", 42)
    assert [(f["step"], f["severity"], f["title"]) for f in findings] == [
        ("review-pr", "must", "Fix the thing"),
        ("validate-pr", "should", "Link an issue"),
        ("review-pr", "may", "Tidy the helper"),
    ]
    assert findings[0]["description"] == "It is broken."
    assert findings[0]["sha"] == "abc1234"
    assert findings[1]["status"] == "open"


def test_collect_findings_skips_entries_without_a_severity(tmp_path):
    _write_state(
        tmp_path,
        "verify.yaml",
        [
            {"title": "Criterion met", "severity": "must", "status": "conforms"},
            {"title": "No severity here", "severity": ""},
        ],
    )
    findings = collect_findings("TomzxCode", "agentic", 42)
    assert [f["title"] for f in findings] == ["Criterion met"]
    assert findings[0]["step"] == "verify-pr"


def test_collect_findings_is_empty_without_a_review_directory(tmp_path):
    assert collect_findings("TomzxCode", "agentic", 7) == []


def test_a_state_file_that_is_not_valid_yaml_is_still_read(tmp_path):
    # A description with an unquoted ": " is invalid YAML (the skills write it
    # that way), so a strict parse fails and the tolerant reader is used.
    directory = tmp_path / "TomzxCode" / "agentic" / "pull-requests" / "42"
    directory.mkdir(parents=True)
    (directory / "review.yaml").write_text(
        "pr: 42\n"
        "findings:\n"
        "  - title: Fix it\n"
        "    description: >-\n"
        "      First line\n"
        "      folded onto one line\n"
        "    severity: must\n"
        "    status: open\n"
        "  - title: Needs quoting\n"
        "    description: A plain scalar: with a colon\n"
        "    severity: should\n"
        "    status: open\n"
    )

    findings = collect_findings("TomzxCode", "agentic", 42)
    assert [(f["severity"], f["title"]) for f in findings] == [("must", "Fix it"), ("should", "Needs quoting")]
    assert findings[0]["description"] == "First line folded onto one line"
    assert findings[1]["description"] == "A plain scalar: with a colon"


def test_findings_endpoint(tmp_path):
    _write_state(tmp_path, "review.yaml", [{"title": "Fix the thing", "severity": "must"}])
    with TestClient(app) as client:
        findings = client.get(
            "/api/reviews/findings/42",
            params={"repository": "TomzxCode/agentic"},
        ).json()
        assert findings == [
            {
                "step": "review-pr",
                "title": "Fix the thing",
                "description": "",
                "severity": "must",
                "status": "open",
                "sha": "abc1234",
            }
        ]
        # A PR with no review directory returns an empty list, not an error.
        assert client.get("/api/reviews/findings/9", params={"repository": "TomzxCode/agentic"}).json() == []
