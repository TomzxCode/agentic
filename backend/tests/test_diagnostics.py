"""Diagnostics: presence and versions of the external commands the app runs."""

from __future__ import annotations

import subprocess

from fastapi.testclient import TestClient
from sqlmodel import Session

from agentic import diagnostics
from agentic.agents.harnesses import seed_harnesses
from agentic.db import create_db_and_tables, engine
from agentic.main import app
from agentic.schemas.settings import DependencyRead


def _spec(command: str = "ghx") -> diagnostics.DependencySpec:
    return next(spec for spec in diagnostics.TOOL_DEPENDENCIES if spec.command == command)


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["cmd"], returncode, stdout=stdout, stderr=stderr)


def test_probe_reports_a_missing_command(monkeypatch):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: None)

    report = diagnostics.probe(_spec())

    assert report.present is False
    assert report.path is None
    assert report.version is None
    assert report.required is False


def test_probe_reports_an_rpc_served_command_as_present(monkeypatch):
    from agentic.config import settings

    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: None)
    monkeypatch.setattr(settings, "ghx_backend", "rpc")

    report = diagnostics.probe(_spec())

    # The server answers in ghx's place, so the tool is present without a
    # local binary; its path and version are only known for a local install.
    assert report.present is True
    assert report.path is None
    assert report.version is None


def test_probe_reads_the_first_version_line(monkeypatch):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: "/usr/bin/ghx")
    monkeypatch.setattr(
        diagnostics.subprocess, "run", lambda *args, **kwargs: _completed(stdout="ghx version 1.2.3\nextra\n")
    )

    report = diagnostics.probe(_spec())

    assert report.present is True
    assert report.path == "/usr/bin/ghx"
    assert report.version == "ghx version 1.2.3"
    assert report.error is None


def test_probe_falls_back_to_stderr_and_tolerates_no_version(monkeypatch):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(diagnostics.subprocess, "run", lambda *args, **kwargs: _completed(stderr="slackx 0.1.0\n"))
    assert diagnostics.probe(_spec("slackx")).version == "slackx 0.1.0"

    # A command that answers --version with nothing is installed, just unversioned.
    monkeypatch.setattr(diagnostics.subprocess, "run", lambda *args, **kwargs: _completed())
    report = diagnostics.probe(_spec("slackx"))
    assert report.present is True
    assert report.version is None
    assert report.error is None


def test_probe_closes_stdin_so_a_server_style_command_cannot_hang(monkeypatch):
    # A harness that ignores --version (pi-acp) starts its ACP loop and reads
    # stdin until it ends; inheriting the server's terminal kept it alive for the
    # whole timeout.
    seen: dict[str, object] = {}

    def record(*args, **kwargs):
        seen.update(kwargs)
        return _completed(stdout="1.0.0\n")

    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: "/usr/bin/opencode")
    monkeypatch.setattr(diagnostics.subprocess, "run", record)

    diagnostics.probe(_spec())

    assert seen["stdin"] is subprocess.DEVNULL


def test_probe_reports_a_timeout(monkeypatch):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: "/usr/bin/ghx")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("ghx", diagnostics.VERSION_TIMEOUT)

    monkeypatch.setattr(diagnostics.subprocess, "run", timeout)

    report = diagnostics.probe(_spec())

    assert report.present is True
    assert report.version is None
    assert report.error is not None and "timed out" in report.error


def test_parse_ghx_repositories_reads_both_row_shapes():
    rows = diagnostics.parse_ghx_repositories(
        "\n".join(
            [
                "REPO                               ISSUES  PRS   CACHED AGE  STATUS         "
                "ISSUE-LIST  ISSUE-VIEW  PR-LIST  PR-VIEW",
                "openchamber/openchamber            2119    2883  23h43m      stale          "
                "33% (6)     100% (5)    —        72% (29)",
                "exolnet/laravel-module             0       1     —           no cache info  "
                "—           —           0% (1)   —",
                "",
            ]
        )
    )

    assert [row.repository for row in rows] == ["openchamber/openchamber", "exolnet/laravel-module"]
    assert rows[0].issues == 2119
    assert rows[0].pull_requests == 2883
    assert rows[0].cached_age == "23h43m"
    assert rows[0].status == "stale"
    assert rows[0].issue_list.percent == 33
    assert rows[0].issue_list.retrievals == 6
    assert rows[0].issue_view.percent == 100
    assert rows[0].pr_list.percent is None
    assert rows[0].pr_view.percent == 72
    assert rows[0].pr_view.retrievals == 29
    assert rows[1].cached_age is None
    assert rows[1].status == "no cache info"
    assert rows[1].pr_list.percent == 0
    assert rows[1].pr_list.retrievals == 1


def test_parse_ghx_repositories_accepts_rows_without_hit_rates():
    # A ghx that predates the hit-rate columns stops at the status.
    rows = diagnostics.parse_ghx_repositories(
        "\n".join(
            [
                "REPO                   ISSUES  PRS   CACHED AGE  STATUS",
                "openchamber/openchamber 1854   2409  14d         stale",
                "exolnet/laravel-module  0       1     —           no cache info",
            ]
        )
    )

    assert [row.repository for row in rows] == ["openchamber/openchamber", "exolnet/laravel-module"]
    assert rows[0].cached_age == "14d"
    assert rows[0].status == "stale"
    assert rows[1].status == "no cache info"
    assert rows[1].issue_list.percent is None
    assert rows[1].pr_view.retrievals == 0


def test_ghx_cache_reports_a_missing_command(monkeypatch):
    monkeypatch.setattr(diagnostics, "run_cli_raw", lambda cmd, timeout: None)

    cache = diagnostics.ghx_cache()

    assert cache.available is False
    assert cache.error is not None and "ghx" in cache.error


def test_ghx_cache_lists_repositories_and_reports_a_failed_listing(monkeypatch):
    output = (
        "REPO           ISSUES  PRS   CACHED AGE  STATUS         ISSUE-LIST  ISSUE-VIEW  PR-LIST  PR-VIEW\n"
        "tomzx/agents   2       3     —           no cache info  —           —           —        71% (7)\n"
    )
    monkeypatch.setattr(
        diagnostics,
        "run_cli_raw",
        lambda cmd, timeout: _completed(stdout=output),
    )

    cache = diagnostics.ghx_cache()

    assert cache.available is True
    assert cache.error is None
    assert cache.repositories[0].repository == "tomzx/agents"
    assert cache.repositories[0].pr_view.percent == 71
    assert cache.repositories[0].pr_view.retrievals == 7

    monkeypatch.setattr(
        diagnostics,
        "run_cli_raw",
        lambda cmd, timeout: _completed(stderr="permission denied", returncode=1),
    )

    failed = diagnostics.ghx_cache()
    assert failed.available is True
    assert failed.error == "permission denied"
    assert failed.repositories == []


def test_slackx_cache_reads_the_json_status(monkeypatch):
    output = (
        '{"workspace": "tomzx", "db_path": "/home/tomzx/.cache/slackx/tomzx/threads.db",'
        ' "channel_count": 12, "user_count": 6, "thread_count": 32, "message_count": 47,'
        ' "read_marker_count": 1, "channels_updated_at": 1788496504.25,'
        ' "users_updated_at": 1790132891.6, "threads_updated_at": 1792116453.9}'
    )
    monkeypatch.setattr(diagnostics, "run_cli_raw", lambda cmd, timeout: _completed(stdout=output))

    cache = diagnostics.slackx_cache()

    assert cache.available is True
    assert cache.workspace == "tomzx"
    assert cache.db_path == "/home/tomzx/.cache/slackx/tomzx/threads.db"
    assert cache.channel_count == 12
    assert cache.user_count == 6
    assert cache.thread_count == 32
    assert cache.message_count == 47
    assert cache.read_marker_count == 1
    assert cache.channels_updated_at is not None
    assert cache.channels_updated_at.tzinfo is not None


def test_slackx_cache_reports_unusable_output(monkeypatch):
    monkeypatch.setattr(diagnostics, "run_cli_raw", lambda cmd, timeout: None)
    missing = diagnostics.slackx_cache()
    assert missing.available is False
    assert missing.error is not None and "slackx" in missing.error

    monkeypatch.setattr(diagnostics, "run_cli_raw", lambda cmd, timeout: _completed(stdout="not json"))
    broken = diagnostics.slackx_cache()
    assert broken.available is True
    assert broken.error is not None and "did not return JSON" in broken.error


def test_collect_lists_the_runtime_tools_and_harnesses(monkeypatch):
    monkeypatch.setattr(
        diagnostics,
        "probe",
        lambda spec: DependencyRead(
            id=spec.id,
            name=spec.name,
            command=spec.command,
            category=spec.category,
            required=spec.required,
            purpose=spec.purpose,
            present=True,
            path=f"/usr/bin/{spec.command}",
            version="1.0.0",
        ),
    )
    monkeypatch.setattr(
        diagnostics,
        "run_cli_raw",
        lambda cmd, timeout: _completed(
            stdout=(
                "REPO  ISSUES  PRS  CACHED AGE  STATUS\ntomzx/agents  2  3  1d  stale\n"
                if cmd[0] == "ghx"
                else '{"channel_count": 1, "user_count": 2, "thread_count": 3,'
                ' "message_count": 4, "read_marker_count": 5}'
            )
        ),
    )

    with Session(engine) as session:
        create_db_and_tables()
        seed_harnesses(session)
        report = diagnostics.collect_diagnostics(session)

    by_id = {dependency.id: dependency for dependency in report.dependencies}
    assert {"python", "git", "ghx", "gh", "slackx"} <= set(by_id)
    assert by_id["python"].category == "runtime"
    assert by_id["python"].version
    assert by_id["git"].required is True
    assert by_id["git"].version == "1.0.0"
    # The seeded presets are probed through their configured commands.
    assert {"harness:opencode", "harness:opencode2", "harness:pi"} <= set(by_id)
    assert by_id["harness:opencode"].category == "harness"
    assert report.ghx_cache.repositories[0].repository == "tomzx/agents"
    assert report.slackx_cache.message_count == 4


def test_diagnostics_endpoint_returns_the_probe_results(monkeypatch):
    monkeypatch.setattr(
        diagnostics,
        "probe",
        lambda spec: DependencyRead(
            id=spec.id,
            name=spec.name,
            command=spec.command,
            category=spec.category,
            purpose=spec.purpose,
            present=spec.id != "slackx",
            path=None if spec.id == "slackx" else f"/usr/bin/{spec.command}",
            version=None if spec.id == "slackx" else "1.0.0",
        ),
    )
    monkeypatch.setattr(
        diagnostics,
        "run_cli_raw",
        lambda cmd, timeout: None,
    )

    with TestClient(app) as client:
        response = client.get("/api/settings/diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert body["checked_at"]
    dependencies = {item["id"]: item for item in body["dependencies"]}
    assert dependencies["ghx"]["present"] is True
    assert dependencies["ghx"]["version"] == "1.0.0"
    assert dependencies["slackx"]["present"] is False
    assert dependencies["slackx"]["version"] is None
    assert body["ghx_cache"]["available"] is False
    assert body["slackx_cache"]["available"] is False
