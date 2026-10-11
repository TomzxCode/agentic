"""Side-effectful services helpers: git, source fetching, and prompt building."""

import subprocess

import pytest

from agentic import services

# --- git ------------------------------------------------------------------


def test_detect_remote_url(monkeypatch, tmp_path):
    monkeypatch.setattr(
        services, "_git", lambda args, cwd, timeout=15: subprocess.CompletedProcess(args, 0, "git@x:o/r.git\n", "")
    )
    assert services.detect_remote_url(str(tmp_path)) == "git@x:o/r.git"

    monkeypatch.setattr(services, "_git", lambda args, cwd, timeout=15: subprocess.CompletedProcess(args, 1, "", ""))
    assert services.detect_remote_url(str(tmp_path)) is None


def test_detect_default_branch_prefers_origin_head(monkeypatch, tmp_path):
    monkeypatch.setattr(
        services, "_git", lambda args, cwd, timeout=15: subprocess.CompletedProcess(args, 0, "origin/develop\n", "")
    )
    assert services.detect_default_branch(str(tmp_path)) == "develop"


def test_detect_default_branch_falls_back_to_main_then_master(monkeypatch, tmp_path):
    def fake(args, cwd, timeout=15):
        if args[0] == "symbolic-ref":
            return subprocess.CompletedProcess(args, 1, "", "")
        if args[:3] == ["rev-parse", "--verify", "main"]:
            return subprocess.CompletedProcess(args, 1, "", "")
        if args[:3] == ["rev-parse", "--verify", "master"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 1, "", "")

    monkeypatch.setattr(services, "_git", fake)
    assert services.detect_default_branch(str(tmp_path)) == "master"


def test_detect_default_branch_none_when_nothing_matches(monkeypatch, tmp_path):
    monkeypatch.setattr(services, "_git", lambda args, cwd, timeout=15: subprocess.CompletedProcess(args, 1, "", ""))
    assert services.detect_default_branch(str(tmp_path)) is None


def test_create_worktree_reuses_an_existing_branch(monkeypatch, tmp_path):
    calls: list = []
    monkeypatch.setattr(
        services,
        "_git",
        lambda args, cwd, timeout=120: (calls.append(args), subprocess.CompletedProcess(args, 0, "", ""))[1],
    )
    services.create_worktree(str(tmp_path), "feature", str(tmp_path / "wt"))
    assert ["worktree", "add", str(tmp_path / "wt"), "feature"] in calls


def test_create_worktree_creates_a_new_branch_from_base(monkeypatch, tmp_path):
    calls: list = []

    def fake(args, cwd, timeout=120):
        calls.append(args)
        if args[:2] == ["rev-parse", "--verify"]:
            return subprocess.CompletedProcess(args, 1, "", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(services, "_git", fake)
    services.create_worktree(str(tmp_path), "new", str(tmp_path / "wt"), base="main")
    assert ["worktree", "add", "-b", "new", str(tmp_path / "wt"), "main"] in calls


def test_create_worktree_raises_on_git_failure(monkeypatch, tmp_path):
    def fake(args, cwd, timeout=120):
        if args[:2] == ["rev-parse", "--verify"]:
            return subprocess.CompletedProcess(args, 1, "", "")
        return subprocess.CompletedProcess(args, 2, "", "boom\n")

    monkeypatch.setattr(services, "_git", fake)
    with pytest.raises(RuntimeError, match="boom"):
        services.create_worktree(str(tmp_path), "b", str(tmp_path / "wt"))


def test_remove_worktree_removes_and_prunes(monkeypatch, tmp_path):
    calls: list = []
    monkeypatch.setattr(
        services,
        "_git",
        lambda args, cwd, timeout=120: (calls.append(args), subprocess.CompletedProcess(args, 0, "", ""))[1],
    )
    services.remove_worktree(str(tmp_path), "/x/wt")
    assert ["worktree", "remove", "--force", "/x/wt"] in calls
    assert ["worktree", "prune"] in calls


# --- cli helper -----------------------------------------------------------
def test_run_cli_returns_none_for_a_missing_command(monkeypatch):
    monkeypatch.setattr(services.shutil, "which", lambda name: None)
    assert services._run_cli(["nope"]) is None


def test_run_cli_returns_stdout_only_on_success(monkeypatch):
    monkeypatch.setattr(services.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(
        services.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "out\n", "")
    )
    assert services._run_cli(["x"]) == "out"

    monkeypatch.setattr(
        services.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, "out", "err")
    )
    assert services._run_cli(["x"]) is None


def test_run_cli_swallows_a_timeout(monkeypatch):
    monkeypatch.setattr(services.shutil, "which", lambda name: "/usr/bin/" + name)

    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired("x", 1)

    monkeypatch.setattr(services.subprocess, "run", boom)
    assert services._run_cli(["x"]) is None


# --- parsing --------------------------------------------------------------
def test_slugify():
    assert services.slugify("Hello, World!") == "hello-world"
    assert services.slugify("") == "item"
    assert services.slugify("x" * 100) == "x" * 48


def test_parse_github_and_slack():
    github = services.parse_github("https://github.com/psf/requests/pull/12")
    assert github is not None
    assert github["kind"] == "pull_request"
    assert github["external_id"] == "psf/requests#12"
    assert services.parse_github("nope") is None

    slack = services.parse_slack("https://acme.slack.com/archives/C1/p1700000000000000")
    assert slack is not None
    assert slack["ts"] == "1700000000.000000"
    assert slack["external_id"] == "C1:1700000000000000"
    assert services.parse_slack("nope") is None


# --- fetching -------------------------------------------------------------
def test_fetch_source_dispatches_and_swallows_errors(monkeypatch):
    calls: list = []
    monkeypatch.setattr(services, "_fetch_github", lambda url, result: calls.append("github"))
    monkeypatch.setattr(services, "_fetch_slack", lambda url, result: calls.append("slack"))
    monkeypatch.setattr(services, "_fetch_url", lambda url, result: calls.append("url"))

    services.fetch_source("github", "https://github.com/o/r/issues/1", None, "t")
    services.fetch_source("slack", "https://x.slack.com/archives/C1/p1", None, "t")
    services.fetch_source("url", "https://e.com", None, "t")
    services.fetch_source("gdrive", "https://docs.google.com/document/d/abc/edit", None, "t")
    services.fetch_source("note", None, None, "t")
    services.fetch_source("slack", None, None, "t")  # no url means nothing to fetch
    assert calls == ["github", "slack", "url", "url"]

    def boom(url, result):
        raise RuntimeError("network down")

    monkeypatch.setattr(services, "_fetch_url", boom)
    result = services.fetch_source("url", "https://e.com", None, "t")
    assert result["content"] == "" and result["title"] == "t"


def test_fetch_github_populates_the_result(monkeypatch):
    monkeypatch.setattr(
        services,
        "fetch_github_issue",
        lambda *args, **kwargs: {"title": "T", "state": "OPEN", "number": 1, "body": "B"},
    )
    result: dict = {"title": "orig", "content": "", "metadata": {}}
    services._fetch_github("https://github.com/o/r/issues/1", result)
    assert result["title"] == "T"
    assert result["content"] == "B"
    assert result["metadata"]["state"] == "OPEN"


def test_fetch_github_ignores_bad_urls_and_missing_issues(monkeypatch):
    result: dict = {"title": "orig", "content": "", "metadata": {}}
    services._fetch_github("https://example.com", result)
    assert result["title"] == "orig"

    monkeypatch.setattr(services, "fetch_github_issue", lambda *args, **kwargs: None)
    services._fetch_github("https://github.com/o/r/issues/1", result)
    assert result["title"] == "orig"


def test_fetch_slack_prefers_show_then_falls_back_to_fetch(monkeypatch):
    calls: list = []

    def fake(cmd, timeout=60):
        calls.append(cmd[2])
        return "transcript" if cmd[2] == "show" else "fallback"

    monkeypatch.setattr(services, "_run_cli", fake)
    result: dict = {"title": "t", "content": "", "metadata": {}}
    services._fetch_slack("https://acme.slack.com/archives/C1/p1700000000000000", result)
    assert result["content"] == "transcript"
    assert result["metadata"]["channel"] == "C1"
    assert calls == ["show"]

    result = {"title": "t", "content": "", "metadata": {}}
    monkeypatch.setattr(services, "_run_cli", lambda cmd, timeout=60: None if cmd[2] == "show" else "fallback")
    services._fetch_slack("https://acme.slack.com/archives/C1/p1700000000000000", result)
    assert result["content"] == "fallback"


def test_fetch_url_extracts_title_and_strips_markup(monkeypatch):
    class Response:
        text = "<html><head><title>Page  Title</title></head><body><style>x</style>Hello <b>world</b></body></html>"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(services.httpx, "get", lambda *args, **kwargs: Response())
    result: dict = {"title": "", "content": "", "metadata": {}}
    services._fetch_url("https://e.com", result)
    assert result["title"] == "Page Title"
    assert "Hello world" in result["content"]
    assert "<b>" not in result["content"]


def test_list_github_issues_returns_none_when_cli_fails(monkeypatch):
    monkeypatch.setattr(services, "_run_cli", lambda cmd, timeout=60: None)
    assert services.list_github_issues("o", "r") is None


def test_list_github_issues_clamps_the_limit(monkeypatch):
    seen: dict = {}

    def fake(cmd, timeout=60):
        seen["limit"] = cmd[cmd.index("--limit") + 1]
        return "[]"

    monkeypatch.setattr(services, "_run_cli", fake)
    assert services.list_github_issues("o", "r", limit=0) == []
    assert seen["limit"] == "1"


def test_fetch_github_issue_returns_none_when_cli_fails(monkeypatch):
    monkeypatch.setattr(services, "_run_cli", lambda cmd, timeout=60: None)
    assert services.fetch_github_issue("o", "r", 1) is None


# --- context prompt -------------------------------------------------------
def test_build_context_prompt_includes_repositories_worktrees_and_items():
    prompt = services.build_context_prompt(
        {
            "title": "T",
            "description": "D",
            "status": "open",
            "priority": 1,
            "repositories": ["/r/a"],
            "worktrees": [{"branch": "b", "path": "/w"}],
            "group": None,
        },
        [{"source": "note", "title": "n", "url": None, "content": "c"}],
    )
    assert "## Description" in prompt and "D" in prompt
    assert "## Repositories" in prompt and "/r/a" in prompt
    assert "## Active worktrees" in prompt and "b at /w" in prompt
    assert "[note] n" in prompt


# --- json extraction ------------------------------------------------------
def test_iter_json_objects_respects_strings_and_braces():
    text = '{"a": "}{"} trailing {"b": 2}'
    assert list(services._iter_json_objects(text)) == ['{"a": "}{"}', '{"b": 2}']


def test_repair_truncated_json_closes_open_structures():
    assert services._repair_truncated_json('{"a": "unterminated') == '{"a": "unterminated"}'
    assert services._repair_truncated_json('{"a": 1}') is None


def test_extract_context_json_coerces_string_steps():
    data = services.extract_context_json('{"summary": "s", "next_steps": ["do a", {"text": "do b", "done": true}]}')
    assert data is not None
    assert data["next_steps"] == [{"text": "do a", "done": False}, {"text": "do b", "done": True}]


def test_worktree_path_slugifies_the_branch():
    path = services.worktree_path("task1", "agentic/Silly Goose")
    assert path.endswith("task1/agentic-silly-goose")
