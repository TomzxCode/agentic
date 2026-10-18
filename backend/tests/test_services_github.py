"""GitHub fetch helpers."""

from agentic.services import github, shell


def test_fetch_github_populates_the_result(monkeypatch):
    monkeypatch.setattr(
        github,
        "fetch_github_issue",
        lambda *args, **kwargs: {
            "title": "T",
            "state": "OPEN",
            "number": 1,
            "body": "B",
            "people": [{"name": "a", "handle": "a"}],
        },
    )
    result: dict = {"title": "orig", "content": "", "metadata": {}}
    github._fetch_github("https://github.com/o/r/issues/1", result)
    assert result["title"] == "T"
    assert result["content"] == "B"
    assert result["metadata"]["state"] == "OPEN"
    # A payload that names no author stores None rather than failing.
    assert result["metadata"]["author"] is None
    # An unmerged PR (no mergedAt) stores None rather than a bogus time.
    assert result["metadata"]["merged_at"] is None
    assert result["people"] == [{"name": "a", "handle": "a"}]


def test_fetch_github_tolerates_a_payload_without_people(monkeypatch):
    monkeypatch.setattr(
        github,
        "fetch_github_issue",
        lambda *args, **kwargs: {"title": "T", "state": "OPEN", "number": 1, "body": "B"},
    )
    result: dict = {"title": "orig", "content": "", "metadata": {}}
    github._fetch_github("https://github.com/o/r/issues/1", result)
    assert result["people"] == []


def test_fetch_github_ignores_bad_urls_and_missing_issues(monkeypatch):
    result: dict = {"title": "orig", "content": "", "metadata": {}}
    github._fetch_github("https://example.com", result)
    assert result["title"] == "orig"

    monkeypatch.setattr(github, "fetch_github_issue", lambda *args, **kwargs: None)
    github._fetch_github("https://github.com/o/r/issues/1", result)
    assert result["title"] == "orig"


def test_list_github_issues_returns_none_when_cli_fails(monkeypatch):
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
    assert github.list_github_issues("o", "r") is None


def test_list_github_issues_clamps_the_limit(monkeypatch):
    seen: dict = {}

    def fake(cmd, timeout=60):
        seen["limit"] = cmd[cmd.index("--limit") + 1]
        return "[]"

    monkeypatch.setattr(shell, "_run_cli", fake)
    assert github.list_github_issues("o", "r", limit=0) == []
    assert seen["limit"] == "1"


def test_fetch_github_issue_returns_none_when_cli_fails(monkeypatch):
    monkeypatch.setattr(shell, "_run_cli", lambda cmd, timeout=60: None)
    assert github.fetch_github_issue("o", "r", 1) is None
