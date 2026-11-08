"""Review scores: the 0-1 values the review steps write into report markers."""

import json

from fastapi.testclient import TestClient

from agentic.config import settings
from agentic.main import app
from agentic.review_scores import collect_review_scores
from agentic.review_store import STEPS


def _marker(step="review-pr", sha="abc1234", verdict="approved", score=1.0, reviewed_at="2026-11-01T10:00:00Z"):
    payload = {"step": step, "sha": sha, "verdict": verdict, "reviewed_at": reviewed_at}
    if score is not None:
        payload["score"] = score
    return f"<!-- {json.dumps(payload)} -->\n"


def _write_pr(root, owner, repo, number, reports, author="alice"):
    """Lay out a PR review directory the way the skills leave it behind."""
    directory = root / owner / repo / "pull-requests" / str(number)
    directory.mkdir(parents=True)
    for name, text in reports.items():
        (directory / name).write_text(text)
    (directory / "gh-pr-view.md").write_text(
        f"#{number} A pull request\n"
        f"OPEN • opened by {author} • 0 comment(s)\n\n"
        f"URL:       https://github.com/{owner}/{repo}/pull/{number}\n"
    )
    return directory


def test_collect_review_scores_reads_markers_author_and_order(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write_pr(
        tmp_path,
        "TomzxCode",
        "agentic",
        42,
        {
            "validate-pr.abc1234.md": _marker(step="validate-pr", score=0.5, reviewed_at="2026-11-02T10:00:00Z"),
            "review-pr.abc1234.md": _marker(score=0.75, reviewed_at="2026-11-01T10:00:00Z"),
            "review-pr.report.md": "ignored",
        },
    )
    _write_pr(
        tmp_path,
        "acme",
        "api",
        7,
        {"review-pr.def5678.md": _marker(sha="def5678", score=1.0, reviewed_at="2026-11-03T10:00:00Z")},
        author="bob",
    )

    runs = collect_review_scores()
    assert [(run["repository"], run["number"], run["step"]) for run in runs] == [
        ("TomzxCode/agentic", 42, "review-pr"),
        ("TomzxCode/agentic", 42, "validate-pr"),
        ("acme/api", 7, "review-pr"),
    ]
    assert runs[0]["author"] == "alice"
    assert runs[0]["score"] == 0.75
    assert runs[0]["source"] == "marker"
    assert runs[2]["author"] == "bob"
    assert runs[0]["reviewed_at"].isoformat() == "2026-11-01T10:00:00+00:00"


def test_a_marker_without_a_score_is_derived_from_findings_and_verdict(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write_pr(
        tmp_path,
        "TomzxCode",
        "agentic",
        42,
        {
            "review-pr.abc1234.md": _marker(score=None, verdict="approved"),
            "review.yaml": "findings:\n  - title: Use the helper\n    severity: should\n    status: open\n",
        },
    )

    run = collect_review_scores()[0]
    # One open SHOULD is a raw 0.80, capped by the yellow (approved-with-gaps)
    # light at 0.75.
    assert run["score"] == 0.75
    assert run["source"] == "derived"


def test_a_report_without_a_json_marker_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write_pr(
        tmp_path,
        "TomzxCode",
        "agentic",
        42,
        {"review-pr.abc1234.md": "<!-- review-pr:abc1234 -->\n# Review\n\nOld format.\n"},
    )

    assert collect_review_scores() == []


def test_a_marker_for_another_step_does_not_score_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write_pr(
        tmp_path,
        "TomzxCode",
        "agentic",
        42,
        {"review-pr.abc1234.md": _marker(step="validate-pr", score=0.25)},
    )

    assert collect_review_scores() == []


def test_the_endpoint_returns_the_runs_and_the_rubric_order(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write_pr(tmp_path, "TomzxCode", "agentic", 42, {"review-pr.abc1234.md": _marker(score=0.75)})

    response = TestClient(app).get("/api/reviews/scores")
    assert response.status_code == 200
    body = response.json()
    assert body["rubrics"] == list(STEPS)
    assert body["root"] == str(tmp_path)
    assert len(body["runs"]) == 1
    run = body["runs"][0]
    assert (run["repository"], run["number"], run["step"], run["score"]) == (
        "TomzxCode/agentic",
        42,
        "review-pr",
        0.75,
    )
    assert run["author"] == "alice"
    assert run["reviewed_at"].startswith("2026-11-01T10:00:00")


def test_a_second_run_of_one_step_is_a_second_point(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sdlc_dir", tmp_path)
    _write_pr(
        tmp_path,
        "TomzxCode",
        "agentic",
        42,
        {
            "review-pr.aaa1111.md": _marker(sha="aaa1111", score=0.25, reviewed_at="2026-11-01T10:00:00Z"),
            "review-pr.bbb2222.md": _marker(sha="bbb2222", score=1.0, reviewed_at="2026-11-05T10:00:00Z"),
        },
    )

    runs = collect_review_scores()
    assert [run["score"] for run in runs] == [0.25, 1.0]
    assert [run["sha"] for run in runs] == ["aaa1111", "bbb2222"]
