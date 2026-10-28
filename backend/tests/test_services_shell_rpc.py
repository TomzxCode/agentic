"""The cli/rpc transport switch for the ghx and slackx helper calls."""

import json
import subprocess

import httpx
import pytest
import structlog

from agentic.config import settings
from agentic.services import github, shell, slack
from agentic.settings_store import get_rpc_overrides


@pytest.fixture(autouse=True)
def _rpc_settings_store(monkeypatch):
    """Replaces the setting-table read with a per-test dict, yielded by the fixture.

    The transport resolves env values first and stored overrides second; tests
    stay hermetic by writing into the dict instead of the database. Tests that
    prove the real database wiring patch the reader themselves.
    """
    stored: dict[str, str] = {}
    monkeypatch.setattr("agentic.settings_store.get_rpc_overrides", lambda: dict(stored))
    yield stored


def _rpc_result(exit_code=0, stdout="", stderr=""):
    """A JSON-RPC response wrapping a ``cli.run`` outcome."""
    return httpx.Response(
        200,
        json={"jsonrpc": "2.0", "id": 1, "result": {"exitCode": exit_code, "stdout": stdout, "stderr": stderr}},
    )


def _rpc_typed(result):
    """A JSON-RPC response whose result is a typed method's payload itself."""
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})


class _FakeSubprocess:
    """Stands in for the subprocess module, without patching the real one."""

    CompletedProcess = subprocess.CompletedProcess
    TimeoutExpired = subprocess.TimeoutExpired

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def run(self, cmd, **kwargs):
        self.calls.append(cmd)
        outcome = self.outcomes.pop(0) if self.outcomes else (0, "out\n", "")
        if isinstance(outcome, Exception):
            raise outcome
        return subprocess.CompletedProcess(cmd, outcome[0], stdout=outcome[1], stderr=outcome[2])


def test_cli_mode_spawns_the_binary_per_call(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "cli")

    def fail_post(*args, **kwargs):
        raise AssertionError("the rpc transport must not be used in cli mode")

    monkeypatch.setattr(shell.httpx, "post", fail_post)
    monkeypatch.setattr(shell.shutil, "which", lambda name: "/usr/bin/" + name)
    fake = _FakeSubprocess()
    monkeypatch.setattr(shell, "subprocess", fake)
    assert shell._run_cli(["ghx", "issue", "list", "--repo", "o/r"]) == "out"
    assert fake.calls == [["ghx", "issue", "list", "--repo", "o/r"]]


def test_the_log_event_names_the_transport(monkeypatch):
    """A ghx call logs its transport, so an rpc call does not read as a spawn."""
    monkeypatch.setattr(settings, "ghx_backend", "cli")
    monkeypatch.setattr(shell.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(shell, "subprocess", _FakeSubprocess())
    with structlog.testing.capture_logs() as logs:
        shell._run_cli(["ghx", "issue", "list", "--repo", "o/r"])
    assert [(entry["event"], entry["mode"]) for entry in logs] == [("tool call", "cli")]

    monkeypatch.setattr(settings, "ghx_backend", "rpc")
    monkeypatch.setattr(settings, "ghx_rpc_url", "http://127.0.0.1:8090")
    monkeypatch.setattr(shell.httpx, "post", lambda url, **kwargs: _rpc_result(stdout="out\n"))
    with structlog.testing.capture_logs() as logs:
        shell._run_cli(["ghx", "issue", "list", "--repo", "o/r"])
    assert [(entry["event"], entry["mode"]) for entry in logs] == [("tool call", "rpc")]


def test_gh_calls_stay_local_even_in_rpc_mode(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "rpc")

    def fail_post(*args, **kwargs):
        raise AssertionError("only ghx and slackx route to the rpc transport")

    monkeypatch.setattr(shell.httpx, "post", fail_post)
    monkeypatch.setattr(shell.shutil, "which", lambda name: "/usr/bin/" + name)
    fake = _FakeSubprocess()
    monkeypatch.setattr(shell, "subprocess", fake)
    assert shell._run_cli(["gh", "api", "user"]) == "out"
    assert fake.calls == [["gh", "api", "user"]]


def test_rpc_mode_sends_the_command_to_the_server(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "rpc")
    monkeypatch.setattr(settings, "ghx_rpc_url", "http://127.0.0.1:8090/")
    monkeypatch.setattr(settings, "ghx_rpc_token", "")
    calls = {}

    def fake_post(url, **kwargs):
        body = kwargs.get("json")
        calls.update(url=url, body=body, headers=kwargs.get("headers"), timeout=kwargs.get("timeout"))
        return _rpc_result(stdout="out\n")

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    assert shell._run_cli(["ghx", "issue", "list", "--repo", "o/r"]) == "out"
    # The endpoint is the configured base plus /rpc, and the argv loses the
    # binary name: the server knows which tool it serves.
    assert calls["url"] == "http://127.0.0.1:8090/rpc"
    assert calls["body"]["method"] == "cli.run"
    assert calls["body"]["params"] == {"args": ["issue", "list", "--repo", "o/r"]}
    assert calls["timeout"] == 60
    # A caller-supplied timeout reaches the request, as it does for a spawn.
    shell._run_cli(["ghx", "cache", "--repo", "o/r"], timeout=300)
    assert calls["timeout"] == 300


def test_rpc_mode_accepts_a_url_that_already_names_rpc(monkeypatch):
    monkeypatch.setattr(settings, "slackx_backend", "rpc")
    monkeypatch.setattr(settings, "slackx_rpc_url", "http://127.0.0.1:8280/rpc")
    calls = {}

    def fake_post(url, **kwargs):
        calls["url"] = url
        return _rpc_result()

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    shell._run_cli(["slackx", "users", "list"])
    assert calls["url"] == "http://127.0.0.1:8280/rpc"


def test_rpc_mode_sends_the_bearer_token_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "slackx_backend", "rpc")
    monkeypatch.setattr(settings, "slackx_rpc_token", "s3cret")
    calls = {}

    def fake_post(url, **kwargs):
        calls["headers"] = kwargs.get("headers")
        return _rpc_result()

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    shell._run_cli(["slackx", "users", "list"])
    assert calls["headers"] == {"Authorization": "Bearer s3cret"}


def test_rpc_failures_read_as_failed_commands(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "rpc")
    responses = iter(
        [
            {"jsonrpc": "2.0", "id": 1, "result": {"exitCode": 2, "stdout": "", "stderr": "boom"}},
            {"jsonrpc": "2.0", "id": 2, "error": {"code": -32000, "message": "cli.run is disabled"}},
            {"jsonrpc": "2.0", "id": 3, "result": "not an object"},
            {"jsonrpc": "2.0", "id": 4, "error": "refused"},
            {"jsonrpc": "2.0", "id": 5, "result": {"exitCode": 0, "stdout": 5, "stderr": None}},
            {"jsonrpc": "2.0", "id": 6, "result": {"exitCode": 3, "stdout": "partial", "stderr": "warn"}},
        ]
    )

    def fake_post(url, **kwargs):
        return httpx.Response(200, json=next(responses))

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    # A non-zero exit code reads exactly as it does in cli mode.
    assert shell._run_cli(["ghx", "repo", "list"]) is None
    # An RPC-level refusal and an unusable result come back as failed commands
    # whose stderr names the cause.
    result = shell.run_cli_raw(["ghx", "repo", "list"])
    assert result is not None and result.returncode == 1
    assert "cli.run is disabled" in result.stderr
    result = shell.run_cli_raw(["ghx", "repo", "list"])
    assert result is not None and result.returncode == 1
    assert "unusable" in result.stderr
    # An error that is not an object is still named, and field values that are
    # not strings read as empty instead of raising.
    result = shell.run_cli_raw(["ghx", "repo", "list"])
    assert result is not None and result.returncode == 1
    assert "refused" in result.stderr
    assert shell._run_cli(["ghx", "repo", "list"]) == ""
    # A genuine non-zero exit code passes through run_cli_raw unchanged.
    result = shell.run_cli_raw(["ghx", "repo", "list"])
    assert result is not None
    assert (result.returncode, result.stdout, result.stderr) == (3, "partial", "warn")


def test_an_http_error_response_names_its_status(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "rpc")
    monkeypatch.setattr(settings, "ghx_rpc_token", "wrong")
    monkeypatch.setattr(shell.httpx, "post", lambda url, **kwargs: httpx.Response(401, text="unauthorized"))
    result = shell.run_cli_raw(["ghx", "repo", "list"])
    assert result is not None and result.returncode == 1
    assert "HTTP 401" in result.stderr


def test_an_unreachable_rpc_server_names_itself_instead_of_reading_as_missing(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "rpc")

    def refused(url, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(shell.httpx, "post", refused)
    assert shell._run_cli(["ghx", "repo", "list"]) is None
    result = shell.run_cli_raw(["ghx", "repo", "list"])
    assert result is not None and result.returncode == 1
    assert "unreachable" in result.stderr


def test_cli_mode_still_reports_a_missing_binary_as_none(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "cli")
    monkeypatch.setattr(shell.shutil, "which", lambda name: None)
    assert shell.run_cli_raw(["ghx", "repo", "list"]) is None


def test_rpc_mode_answers_available_without_the_local_binary(monkeypatch):
    monkeypatch.setattr(shell.shutil, "which", lambda name: None)
    assert shell._cli_available("ghx") is False
    monkeypatch.setattr(settings, "ghx_backend", "rpc")
    assert shell._cli_available("ghx") is True
    # The switch is per tool: slackx without its own rpc setting stays local.
    monkeypatch.setattr(settings, "slackx_backend", "cli")
    assert shell._cli_available("slackx") is False


def test_managed_mode_calls_the_endpoint_the_server_supplies(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "managed")
    # The rpc settings do not apply: the server starts the tool itself and
    # generates the token its process requires. A configured token is ignored.
    monkeypatch.setattr(settings, "ghx_rpc_url", "http://127.0.0.1:9999")
    monkeypatch.setattr(settings, "ghx_rpc_token", "configured-but-unused")
    monkeypatch.setattr(
        shell.managed_tools,
        "endpoint",
        lambda tool, backend=None: ("http://127.0.0.1:8080/rpc", "generated"),
    )
    calls = {}

    def fake_post(url, **kwargs):
        calls.update(url=url, headers=kwargs.get("headers"))
        return _rpc_result(stdout="out\n")

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    assert shell._run_cli(["ghx", "repo", "list"]) == "out"
    assert calls["url"] == "http://127.0.0.1:8080/rpc"
    assert calls["headers"] == {"Authorization": "Bearer generated"}


def test_managed_mode_still_needs_the_local_binary(monkeypatch):
    monkeypatch.setattr(shell.shutil, "which", lambda name: None)
    monkeypatch.setattr(settings, "slackx_backend", "managed")
    # Unlike rpc mode, this server has to run the tool, so a missing binary is
    # reported as unavailable instead of silently standing in for it.
    assert shell._cli_available("slackx") is False
    # The transport is per tool: ghx without its own setting stays local.
    assert shell._cli_available("ghx") is False


def test_managed_mode_sends_typed_methods_like_rpc_mode(monkeypatch):
    monkeypatch.setattr(settings, "slackx_backend", "managed")

    def fake_post(url, **kwargs):
        assert url == "http://127.0.0.1:8280/rpc"
        assert kwargs["json"]["method"] == "users.list"
        return _rpc_typed({"user_count": 1, "users": [{"id": "U0123ABCDEF", "real_name": "Tom"}]})

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    assert slack.slack_user_names() == {"U0123ABCDEF": "Tom"}


def test_list_github_issues_runs_over_the_typed_method(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "rpc")
    payload = [
        {
            "number": 7,
            "title": "A title",
            "url": "https://github.com/o/r/issues/7",
            "state": "OPEN",
            "author": {"login": "someone"},
            "labels": [],
            "body": "A body",
        }
    ]

    def fake_post(url, **kwargs):
        body = kwargs["json"]
        assert body["method"] == "issue.list"
        assert body["params"] == {"repo": "o/r", "state": "open", "limit": 20}
        return _rpc_typed({"items": payload, "total": 1, "source": "cache"})

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    # The typed result is unwrapped back into the array the CLI would print,
    # so the caller parses it unchanged.
    issues = github.list_github_issues("o", "r")
    assert issues == [
        {
            "number": 7,
            "title": "A title",
            "url": "https://github.com/o/r/issues/7",
            "state": "OPEN",
            "author": "someone",
            "labels": [],
            "body": "A body",
        }
    ]


def test_list_github_pulls_tolerates_the_typed_methods_full_records(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "rpc")
    # The typed pr.list returns whole records, not the field selection the CLI
    # was given; the caller reads only the fields it knows.
    record = {
        "number": 3,
        "title": "A pull request",
        "url": "https://github.com/o/r/pull/3",
        "state": "OPEN",
        "isDraft": True,
        "mergedAt": None,
        "createdAt": "2026-10-01T00:00:00Z",
        "author": {"login": "someone"},
        "labels": [{"name": "bug"}],
        "body": "ignored extra field",
    }

    def fake_post(url, **kwargs):
        assert kwargs["json"]["method"] == "pr.list"
        return _rpc_typed({"items": [record], "total": 1, "source": "cache"})

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    pulls = github.list_github_pulls("o", "r")
    assert pulls == [
        {
            "kind": "pr",
            "number": 3,
            "title": "A pull request",
            "url": "https://github.com/o/r/pull/3",
            "state": "OPEN",
            "is_draft": True,
            "merged_at": None,
            "created_at": "2026-10-01T00:00:00Z",
            "author": "someone",
            "labels": ["bug"],
        }
    ]


def test_fetch_github_issue_runs_over_the_typed_view(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "rpc")
    record = {
        "number": 7,
        "title": "T",
        "url": "u",
        "state": "OPEN",
        "author": {"login": "a"},
        "labels": [],
        "body": "b",
    }

    def fake_post(url, **kwargs):
        body = kwargs["json"]
        assert body["method"] == "issue.view"
        assert body["params"] == {"repo": "o/r", "number": 7}
        return _rpc_typed(record)

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    issue = github.fetch_github_issue("o", "r", 7)
    assert issue is not None and issue["number"] == 7

    def fake_pr_post(url, **kwargs):
        assert kwargs["json"]["method"] == "pr.view"
        return _rpc_typed({**record, "isDraft": False})

    monkeypatch.setattr(shell.httpx, "post", fake_pr_post)
    pull = github.fetch_github_issue("o", "r", 7, kind="pull_request")
    assert pull is not None and pull["is_draft"] is False


def test_refresh_github_cache_runs_over_typed_cache_refresh(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "rpc")

    def fake_post(url, **kwargs):
        assert kwargs["json"]["method"] == "cache.refresh"
        assert kwargs["json"]["params"] == {"repo": "o/r", "force": False}
        return _rpc_typed({"repo": "o/r", "issues": 1, "prs": 0})

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    assert github.refresh_github_cache("o", "r") is True


def test_refresh_github_cache_passes_a_single_type_over_the_typed_method(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "rpc")

    def fake_post(url, **kwargs):
        assert kwargs["json"]["method"] == "cache.refresh"
        assert kwargs["json"]["params"] == {"repo": "o/r", "force": False, "type": "prs"}
        return _rpc_typed({"repo": "o/r", "issues": 0, "prs": 2})

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    assert github.refresh_github_cache("o", "r", types="prs") is True


def test_list_cached_repositories_runs_over_the_typed_method(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "rpc")

    def fake_post(url, **kwargs):
        assert kwargs["json"]["method"] == "repo.list"
        return _rpc_typed(
            {
                "repos": [
                    {"label": "o/warm", "cachedAt": "2026-10-20T00:00:00Z", "fresh": True},
                    {"label": "o/cold", "prCount": 2},
                ]
            }
        )

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    assert github.list_cached_repositories() == {"o/warm"}


def test_slack_user_names_run_over_the_typed_method(monkeypatch):
    monkeypatch.setattr(settings, "slackx_backend", "rpc")
    users = [{"id": "U0123ABCDEF", "name": "tomzx", "real_name": "Tom"}]

    def fake_post(url, **kwargs):
        body = kwargs["json"]
        assert body["method"] == "users.list"
        assert body["params"] == {"fields": "id,name,real_name"}
        return _rpc_typed({"user_count": 1, "users": users})

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    assert slack.slack_user_names() == {"U0123ABCDEF": "Tom"}


def test_slack_user_name_runs_over_the_typed_method(monkeypatch):
    monkeypatch.setattr(settings, "slackx_backend", "rpc")

    def fake_post(url, **kwargs):
        body = kwargs["json"]
        assert body["method"] == "users.get"
        assert body["params"]["user"] == "U0123ABCDEF"
        return _rpc_typed({"user_count": 1, "users": [{"id": "U0123ABCDEF", "real_name": "Tom"}]})

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    assert slack.slack_user_name("U0123ABCDEF") == "Tom"


def test_resolve_slack_channel_name_runs_over_the_typed_method(monkeypatch):
    monkeypatch.setattr(settings, "slackx_backend", "rpc")

    def fake_post(url, **kwargs):
        body = kwargs["json"]
        assert body["method"] == "channels.get"
        assert body["params"] == {"channel": "C0123ABCDEF", "fields": "id,name"}
        return _rpc_typed({"channel_count": 1, "channels": [{"id": "C0123ABCDEF", "name": "test"}]})

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    assert slack.resolve_slack_channel_name("C0123ABCDEF") == "test"


def test_resolve_slack_channel_name_uses_the_single_channel_command(monkeypatch):
    monkeypatch.setattr(settings, "slackx_backend", "cli")
    seen = {}

    def fake_run_cli(cmd, timeout=30):
        seen["cmd"] = cmd
        return json.dumps({"channel_count": 1, "channels": [{"id": "C0123ABCDEF", "name": "test"}]})

    monkeypatch.setattr(slack.shell, "_run_cli", fake_run_cli)
    assert slack.resolve_slack_channel_name("C0123ABCDEF") == "test"
    # `channels list` takes no positional channel; the single-channel command
    # is `channels get`.
    assert seen["cmd"] == ["slackx", "channels", "get", "C0123ABCDEF", "--json", "--fields", "id,name"]


def test_fetch_slack_mixes_the_typed_read_with_the_cli_run_fallback(monkeypatch):
    monkeypatch.setattr(settings, "slackx_backend", "rpc")
    thread = {
        "channel": "C0123ABCDEF",
        "channel_name": "test",
        "thread_ts": "1660000000.000100",
        "message_count": 1,
        "messages": [{"user": "U0123ABCDEF", "text": "hello", "ts": "1660000000.000100"}],
    }
    methods = []

    def fake_post(url, **kwargs):
        body = kwargs["json"]
        methods.append(body["method"])
        if body["method"] == "conversations.get":
            return _rpc_typed(thread)
        if body["method"] == "users.list":
            return _rpc_typed({"user_count": 1, "users": [{"id": "U0123ABCDEF", "name": "tom"}]})
        # The --fetch variant prints rendered text only the CLI renders, so it
        # still goes through cli.run.
        assert body["method"] == "cli.run"
        assert body["params"]["args"][:3] == [
            "conversations",
            "show",
            "https://test.slack.com/archives/C0123ABCDEF/p1660000000000100",
        ]
        return _rpc_result(stdout="rendered thread text")

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    result = {}
    from agentic.services.slack import _fetch_slack

    _fetch_slack("https://test.slack.com/archives/C0123ABCDEF/p1660000000000100", result)
    assert result["content"] == "rendered thread text"
    assert result["people"] == [{"name": "tom", "handle": "U0123ABCDEF", "source": "slack"}]
    # The typed read resolved the channel name into the title.
    assert "#test" in result["title"]
    assert methods.count("cli.run") == 1  # only the --fetch text read
    assert "conversations.get" in methods


def test_unmapped_commands_still_run_through_cli_run(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "rpc")

    def fake_post(url, **kwargs):
        assert kwargs["json"]["method"] == "cli.run"
        return _rpc_result(stdout="a table")

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    # Without --json the typed list does not match what the caller wants.
    assert shell._run_cli(["ghx", "issue", "list", "--repo", "o/r"]) == "a table"


def test_ghx_cache_keeps_the_table_path_for_its_hit_rates(monkeypatch):
    """ghx_cache stays on the CLI table: only it carries the hit-rate columns."""
    from agentic import diagnostics
    from agentic.diagnostics import ghx_cache

    monkeypatch.setattr(settings, "ghx_backend", "rpc")

    def fail_post(url, **kwargs):
        raise AssertionError("only the table read may run, through run_cli_raw")

    monkeypatch.setattr(shell.httpx, "post", fail_post)

    def fake_run_cli(cmd, timeout):
        # The table read has no typed method (repo.list returns JSON only), so
        # it runs through the CLI; the stub sits on the diagnostics module's own
        # binding of run_cli_raw.
        assert cmd == ["ghx", "repo", "list"]
        return subprocess.CompletedProcess(cmd, 0, stdout="o/r\t2\t1\t15d\tstale", stderr="")

    monkeypatch.setattr(diagnostics, "run_cli_raw", fake_run_cli)
    report = ghx_cache()
    assert report.available is True
    assert (report.repositories[0].repository, report.repositories[0].status) == ("o/r", "stale")


def test_slackx_cache_reads_the_typed_cache_status(monkeypatch):
    from agentic.diagnostics import slackx_cache

    monkeypatch.setattr(settings, "slackx_backend", "rpc")
    status = {
        "workspace": "test",
        "db_path": "/x/threads.db",
        "channel_count": 2,
        "user_count": 3,
        "thread_count": 1,
        "message_count": 9,
        "read_marker_count": 0,
        "channels_updated_at": 1760000000.0,
        "users_updated_at": None,
        "threads_updated_at": None,
    }

    def fake_post(url, **kwargs):
        assert kwargs["json"]["method"] == "cache.status"
        return _rpc_typed(status)

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    report = slackx_cache()
    assert report.available is True
    assert (report.workspace, report.channel_count, report.user_count, report.message_count) == ("test", 2, 3, 9)


def test_a_stored_override_switches_the_transport_without_a_restart(monkeypatch, _rpc_settings_store):
    monkeypatch.setattr(shell.shutil, "which", lambda name: None)  # no local binary
    calls = {}

    def fake_post(url, **kwargs):
        calls["url"] = url
        return _rpc_result(stdout="{}")

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    assert shell._run_cli(["ghx", "repo", "list"]) is None  # env says cli, no binary

    _rpc_settings_store.update({"ghx_backend": "rpc", "ghx_rpc_url": "http://127.0.0.1:19999"})
    assert shell._run_cli(["ghx", "repo", "list"]) == "{}"
    assert calls["url"] == "http://127.0.0.1:19999/rpc"


def test_a_stored_cli_override_wins_over_an_rpc_environment(monkeypatch, _rpc_settings_store):
    monkeypatch.setattr(settings, "ghx_backend", "rpc")

    def fail_post(*args, **kwargs):
        raise AssertionError("a stored cli override must win over the environment")

    monkeypatch.setattr(shell.httpx, "post", fail_post)
    monkeypatch.setattr(shell.shutil, "which", lambda name: "/usr/bin/" + name)
    fake = _FakeSubprocess()
    monkeypatch.setattr(shell, "subprocess", fake)
    _rpc_settings_store["ghx_backend"] = "cli"
    assert shell._run_cli(["ghx", "repo", "list"]) == "out"
    assert fake.calls == [["ghx", "repo", "list"]]


def test_a_stored_empty_value_keeps_the_environment(monkeypatch, _rpc_settings_store):
    monkeypatch.setattr(settings, "slackx_backend", "rpc")
    monkeypatch.setattr(settings, "slackx_rpc_url", "http://127.0.0.1:8280")
    _rpc_settings_store.update({"slackx_rpc_url": "", "slackx_rpc_token": "t0ken"})
    # A blank stored value is no opinion: the environment's URL still applies,
    # while the token override next to it does not.
    assert shell._rpc_endpoint("slackx") == ("http://127.0.0.1:8280/rpc", "t0ken")


def test_an_unreadable_settings_store_falls_back_to_the_environment(monkeypatch):
    def broken():
        raise RuntimeError("database is wedged")

    monkeypatch.setattr("agentic.settings_store.get_rpc_overrides", broken)
    monkeypatch.setattr(settings, "ghx_backend", "rpc")
    monkeypatch.setattr(settings, "ghx_rpc_url", "http://127.0.0.1:19999")
    # The environment's rpc settings still resolve; the failure only drops the
    # stored overrides.
    assert shell._rpc_endpoint("ghx") == ("http://127.0.0.1:19999/rpc", "")


def test_get_rpc_overrides_reads_the_setting_table(monkeypatch):
    """The real wiring: a stored row reaches the transport, then is cleaned up."""
    from sqlmodel import Session

    from agentic.db import create_db_and_tables, engine
    from agentic.models.system import Setting

    monkeypatch.setattr("agentic.settings_store.get_rpc_overrides", get_rpc_overrides)
    monkeypatch.setattr(settings, "ghx_backend", "cli")
    monkeypatch.setattr(settings, "ghx_rpc_url", "http://127.0.0.1:8090")
    monkeypatch.setattr(settings, "ghx_rpc_token", "")
    create_db_and_tables()
    with Session(engine) as session:
        row = session.get(Setting, "ghx_backend")
        if row is None:
            session.add(Setting(key="ghx_backend", value="rpc"))
        else:
            row.value = "rpc"
        session.commit()
    try:
        assert get_rpc_overrides().get("ghx_backend") == "rpc"
        # The stored backend wins while the URL and token still come from the
        # environment.
        assert shell._rpc_endpoint("ghx") == ("http://127.0.0.1:8090/rpc", "")
    finally:
        with Session(engine) as session:
            row = session.get(Setting, "ghx_backend")
            if row is not None:
                session.delete(row)
                session.commit()


def test_list_my_open_pulls_passes_the_author_over_the_typed_method(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "rpc")
    record = {
        "number": 3,
        "title": "Mine",
        "url": "https://github.com/o/r/pull/3",
        "isDraft": False,
        "createdAt": "2026-10-01T00:00:00Z",
        "updatedAt": "2026-10-02T00:00:00Z",
        "reviewDecision": "APPROVED",
        "author": {"login": "tomzx"},
        "checks": {"state": "SUCCESS", "total": 2},
        "reviewThreads": {"total": 1, "open": 0},
        "reviews": [{"author": {"login": "alice"}, "state": "APPROVED"}],
        "reviewRequests": [],
    }

    def fake_post(url, **kwargs):
        body = kwargs["json"]
        assert body["method"] == "pr.list"
        # The typed method ignores the --json field list but must not drop the
        # author filter, or another user's pull requests would read as mine.
        assert body["params"] == {"repo": "o/r", "state": "open", "author": "tomzx", "limit": 500}
        return _rpc_typed({"items": [record], "total": 1, "source": "cache"})

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    pulls = github.list_my_open_pulls(["o/r"], "tomzx")

    assert pulls is not None
    assert [pull["number"] for pull in pulls] == [3]
    assert pulls[0]["ci"] == "success"
    assert pulls[0]["threads_total"] == 1


def test_fetch_pull_checks_runs_over_the_typed_method(monkeypatch):
    monkeypatch.setattr(settings, "ghx_backend", "rpc")

    def fake_post(url, **kwargs):
        assert kwargs["json"]["method"] == "pr.checks"
        assert kwargs["json"]["params"] == {"repo": "o/r", "number": 12}
        return _rpc_typed(
            {
                "state": "FAILURE",
                "total": 1,
                "checks": [
                    {
                        "type": "CheckRun",
                        "name": "build",
                        "status": "COMPLETED",
                        "conclusion": "FAILURE",
                        "url": "https://ci/1",
                    }
                ],
            }
        )

    monkeypatch.setattr(shell.httpx, "post", fake_post)
    report = github.fetch_pull_checks("o", "r", 12)

    assert report is not None
    assert report["rollup"] == "failure"
    assert [(check["name"], check["state"]) for check in report["checks"]] == [("build", "failure")]
