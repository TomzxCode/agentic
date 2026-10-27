"""Low-level process helpers shared by the git, GitHub, and Slack fetchers.

They live in one module so there is a single place to stub a subprocess in tests.
The ghx and slackx calls can also run against the tool's own JSON-RPC server
(``ghx rpc serve``, ``slackx rpc serve``) instead of a local spawn; the
``AGENTIC_GHX_BACKEND`` and ``AGENTIC_SLACKX_BACKEND`` settings pick the mode.
The ``managed`` mode runs the tool's serve process from this server, so it
supplies the endpoint itself and needs no URL or token.
"""

from __future__ import annotations

import itertools
import json
import shutil
import subprocess
import time
from typing import Any

import httpx
import structlog

from .. import debug as _debug
from ..config import settings
from .managed_tools import managed_tools

log = structlog.get_logger(__name__)

# The helper CLIs whose every invocation is logged at info level, so the
# server's external calls (and their arguments) are visible while it runs.
_LOGGED_CLIS = frozenset({"ghx", "slackx"})

# Each rpc-capable CLI's settings keys, in (backend, url, token) order. They
# are Settings-page keys (see ``settings_store.RPC_SETTING_KEYS``) layered over
# the matching ``AGENTIC_`` environment values.
_RPC_SETTING_KEYS = {
    "ghx": ("ghx_backend", "ghx_rpc_url", "ghx_rpc_token"),
    "slackx": ("slackx_backend", "slackx_rpc_url", "slackx_rpc_token"),
}

# JSON-RPC request ids, incremented per call.
_rpc_ids = itertools.count(1)


def _log_tool_call(cmd: list[str], mode: str) -> None:
    """Log an invocation of a tracked helper CLI (ghx, slackx) at info level.

    The transport is part of the event: the same argv runs as a local spawn in
    ``cli`` mode and as a call to the tool's own server in ``rpc``/``managed``
    mode, so a log line without it reads as a local process either way.
    """
    if cmd and cmd[0] in _LOGGED_CLIS:
        log.info("tool call", cmd=cmd, mode=mode)


def _stored_overrides(keys: tuple[str, ...]) -> dict[str, str]:
    """The rpc settings stored on the Settings page, or {} when unreadable.

    The late import dodges a cycle: the settings store reaches back here
    through ``services.github``. A read that fails (no table yet, a wedged
    database) falls back to the environment values rather than failing calls.
    """
    from ..settings_store import get_rpc_overrides

    try:
        stored = get_rpc_overrides()
    except Exception as exc:
        log.warning("rpc settings unreadable", error=str(exc))
        return {}
    return {key: stored[key] for key in keys if key in stored}


def _rpc_config(cli: str) -> tuple[str, str, str] | None:
    """A tool's (backend, url, token): stored overrides win over the environment.

    Read per call, so flipping the switch on the Settings page (or editing a
    stored value) takes effect without a restart, also in the worker. A stored
    empty value is no opinion: the environment's value still applies, so
    clearing a field on the Settings page returns to the default.
    """
    keys = _RPC_SETTING_KEYS.get(cli)
    if keys is None:
        return None
    values = {key: getattr(settings, key) for key in keys}
    values.update({key: value for key, value in _stored_overrides(keys).items() if value != ""})
    return values[keys[0]], values[keys[1]], values[keys[2]]


def _rpc_endpoint(cli: str) -> tuple[str, str] | None:
    """The (JSON-RPC URL, bearer token) for a helper CLI, when it has a server.

    A managed tool needs no configuration: this server starts it and supplies
    its endpoint, so the URL and token settings do not apply. Otherwise the
    configured URL is the server's base and the JSON-RPC endpoint lives at
    ``/rpc`` under it (a URL that already names ``/rpc`` also works). None when
    the CLI has no rpc server for this call, which includes every other command
    this module runs (``git``, ``gh``).
    """
    config = _rpc_config(cli)
    if config is None:
        return None
    managed = managed_tools.endpoint(cli, config[0])
    if managed is not None:
        return managed
    if config[0] != "rpc":
        return None
    base = config[1].strip().rstrip("/")
    if base.endswith("/rpc"):
        base = base[: -len("/rpc")]
    return f"{base}/rpc", config[2].strip()


def _rpc_post(
    endpoint: tuple[str, str], method: str, params: dict[str, Any], cmd: list[str], timeout: int
) -> tuple[int, Any, str]:
    """POST one JSON-RPC request: ``(exit code, result, error text)``.

    Failures (an unreachable server, an RPC-level error, an unusable answer)
    read as exit code 1 with the reason as the error text, so every caller
    treats them like a failed command. There is no fall back to a local spawn:
    rpc mode is an explicit choice, and a downed server must not quietly turn
    into local processes reading a different cache.
    """
    url, token = endpoint
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    payload = {"jsonrpc": "2.0", "id": next(_rpc_ids), "method": method, "params": params}
    try:
        # trust_env=False: the servers are local-first endpoints, and a proxy
        # environment would otherwise hijack loopback rpc calls.
        response = httpx.post(url, json=payload, headers=headers, timeout=timeout, trust_env=False)
        if response.status_code != 200:
            # A bad token or a stopped server answers HTTP, not JSON-RPC, and
            # the status names which.
            reason = f"{cmd[0]} rpc server answered HTTP {response.status_code}"
            log.info("cli fetch failed", cmd=cmd[0], error=reason)
            return 1, None, reason
        data = response.json()
    except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
        log.info("cli fetch failed", cmd=cmd[0], error=f"rpc server unreachable: {exc}")
        return 1, None, f"{cmd[0]} rpc server unreachable: {exc}"
    if not isinstance(data, dict):
        log.info("cli fetch failed", cmd=cmd[0], error="rpc response was not an object")
        return 1, None, f"{cmd[0]} rpc server returned an unusable response"
    error = data.get("error")
    if error is not None:
        message = error.get("message") if isinstance(error, dict) else error
        reason = f"{cmd[0]} rpc error: {message or 'unknown rpc error'}"
        log.info("cli fetch failed", cmd=cmd[0], error=reason)
        return 1, None, reason
    result = data.get("result")
    if not isinstance(result, dict):
        log.info("cli fetch failed", cmd=cmd[0], error="rpc result was not an object")
        return 1, None, f"{cmd[0]} rpc server returned an unusable result"
    return 0, result, ""


def _rpc_cli_run(endpoint: tuple[str, str], cmd: list[str], timeout: int) -> tuple[int, str, str]:
    """Run a command line through the server's ``cli.run`` method.

    The argv goes over the wire without the binary name; the server knows which
    tool it serves and spawns the command as its own child. That child spawn is
    what the typed dispatch below avoids for the commands it covers.
    """
    code, result, error = _rpc_post(endpoint, "cli.run", {"args": cmd[1:]}, cmd, timeout)
    if code != 0:
        return 1, "", error
    raw_code = result.get("exitCode")
    exit_code = raw_code if isinstance(raw_code, int) and not isinstance(raw_code, bool) else 1
    stdout = result.get("stdout")
    stderr = result.get("stderr")
    return (
        exit_code,
        stdout if isinstance(stdout, str) else "",
        stderr if isinstance(stderr, str) else "",
    )


def _argv_value(args: list[str], flag: str) -> str | None:
    """The value that follows ``--flag`` in an argv, or None when absent."""
    try:
        return args[args.index(flag) + 1]
    except (ValueError, IndexError):
        return None


def _typed_ghx_list(
    endpoint: tuple[str, str], method: str, args: list[str], timeout: int
) -> tuple[int, str, str] | None:
    """``issue list`` / ``pr list`` through their typed methods.

    The CLI prints a bare array of records; the typed methods wrap the same
    records (pr.list without the field selection, so a superset the callers
    read field-by-field) in ``{items, total, source}``, and the adapter
    unwraps back to the array.
    """
    repo = _argv_value(args, "--repo")
    if not repo or "--json" not in args:
        return None
    params: dict[str, Any] = {"repo": repo}
    state = _argv_value(args, "--state")
    if state:
        params["state"] = state
    author = _argv_value(args, "--author")
    if author:
        params["author"] = author
    limit = _argv_value(args, "--limit")
    if limit is not None:
        # The CLI would reject a non-numeric limit; fall back to it instead of
        # silently asking the server for its default.
        if not limit.isdigit():
            return None
        params["limit"] = int(limit)
    code, result, error = _rpc_post(endpoint, method, params, ["ghx", *args], timeout)
    if code != 0:
        return 1, "", error
    items = result.get("items")
    if not isinstance(items, list):
        return 1, "", "ghx rpc server returned an unusable result"
    return 0, json.dumps(items), ""


def _typed_ghx_view(endpoint: tuple[str, str], kind: str, args: list[str], timeout: int) -> tuple[int, str, str] | None:
    """``issue view`` / ``pr view`` through their typed methods."""
    repo = _argv_value(args, "--repo")
    number = args[2] if len(args) > 2 else ""
    if not repo or "--json" not in args or not number.isdigit():
        return None
    code, result, error = _rpc_post(
        endpoint, f"{kind}.view", {"repo": repo, "number": int(number)}, ["ghx", *args], timeout
    )
    if code != 0:
        return 1, "", error
    # The typed view returns the same bare record the CLI's --json prints.
    return 0, json.dumps(result), ""


def _typed_ghx_cache(endpoint: tuple[str, str], args: list[str], timeout: int) -> tuple[int, str, str] | None:
    """``cache --repo X [--force]`` through cache.refresh.

    A plain ``ghx cache`` is the delta fetch, so it maps to the same method
    without ``force``. Any other flag changes what the CLI would fetch, so it
    stays on cli.run rather than being silently dropped.
    """
    repo = _argv_value(args, "--repo")
    if not repo:
        return None
    for flag in ("--since", "--type", "--cache-duration", "--retries", "--if-stale"):
        if flag in args:
            return None
    force = "--force" in args
    params = {"repo": repo, "force": force}
    code, result, error = _rpc_post(endpoint, "cache.refresh", params, ["ghx", *args], timeout)
    if code != 0:
        return 1, "", error
    return 0, json.dumps(result), ""


def _typed_ghx_checks(endpoint: tuple[str, str], args: list[str], timeout: int) -> tuple[int, str, str] | None:
    """``pr checks`` through pr.checks."""
    repo = _argv_value(args, "--repo")
    number = args[2] if len(args) > 2 else ""
    if not repo or "--json" not in args or not number.isdigit():
        return None
    code, result, error = _rpc_post(
        endpoint, "pr.checks", {"repo": repo, "number": int(number)}, ["ghx", *args], timeout
    )
    if code != 0:
        return 1, "", error
    return 0, json.dumps(result), ""


def _typed_slackx(
    endpoint: tuple[str, str], method: str, target_key: str, args: list[str], timeout: int
) -> tuple[int, str, str] | None:
    """A slackx read through its typed method.

    The typed payloads share the CLI's JSON builders (users, channels, and
    thread views), so the whole result is the stdout the caller expects.
    """
    if "--json" not in args:
        return None
    params: dict[str, Any] = {}
    if target_key:
        value = args[2] if len(args) > 2 else ""
        # A flag in the target position means an argv shape we did not expect;
        # let cli.run give it the command's own usage error.
        if not value or value.startswith("--"):
            return None
        params[target_key] = value
    fields = _argv_value(args, "--fields")
    if fields:
        params["fields"] = fields
    code, result, error = _rpc_post(endpoint, method, params, ["slackx", *args], timeout)
    if code != 0:
        return 1, "", error
    return 0, json.dumps(result), ""


def _typed_dispatch(cmd: list[str], endpoint: tuple[str, str], timeout: int) -> tuple[int, str, str] | None:
    """Run a command through its tool's typed RPC methods when one covers it.

    A typed method runs inside the server process against its cache; cli.run,
    the fallback, makes the server spawn a fresh tool binary per call (for
    slackx, a whole Python interpreter). A handler that does not recognize the
    argv returns None and the command goes to cli.run, which also keeps
    `--allow-exec=false` servers serving every mapped read.
    """
    tool, args = cmd[0], cmd[1:]
    if tool == "ghx":
        head = tuple(args[:2])
        if head == ("issue", "list"):
            return _typed_ghx_list(endpoint, "issue.list", args, timeout)
        if head == ("pr", "list"):
            return _typed_ghx_list(endpoint, "pr.list", args, timeout)
        if head in (("issue", "view"), ("pr", "view")):
            return _typed_ghx_view(endpoint, head[0], args, timeout)
        if head == ("pr", "checks"):
            return _typed_ghx_checks(endpoint, args, timeout)
        if args[:1] == ["cache"]:
            return _typed_ghx_cache(endpoint, args, timeout)
    if tool == "slackx":
        head = tuple(args[:2])
        if head == ("cache", "status"):
            return _typed_slackx(endpoint, "cache.status", "", args, timeout)
        if head == ("users", "list"):
            return _typed_slackx(endpoint, "users.list", "", args, timeout)
        if head == ("users", "get"):
            return _typed_slackx(endpoint, "users.get", "user", args, timeout)
        # One named channel: the CLI's single-channel command is
        # `channels get` (channels list takes no positional).
        if head == ("channels", "get"):
            return _typed_slackx(endpoint, "channels.get", "channel", args, timeout)
        # The --fetch variant prints rendered text only the CLI renders, so it
        # stays on cli.run; the structured --json read maps to conversations.get.
        if head == ("conversations", "show"):
            return _typed_slackx(endpoint, "conversations.get", "target", args, timeout)
    return None


def _cli_run(cmd: list[str], timeout: int) -> tuple[int, str, str] | None:
    """Run a helper CLI in its configured mode: ``(returncode, stdout, stderr)``.

    None only when the command could not run at all: the binary is missing from
    PATH or the spawn failed (cli mode). In rpc mode the server answers with an
    outcome for every call.
    """
    started = time.perf_counter()
    endpoint = _rpc_endpoint(cmd[0])
    if endpoint is None and shutil.which(cmd[0]) is None:
        return None
    mode = "rpc" if endpoint is not None else "cli"
    _log_tool_call(cmd, mode)
    try:
        if endpoint is not None:
            typed = _typed_dispatch(cmd, endpoint, timeout)
            if typed is not None:
                duration_ms = (time.perf_counter() - started) * 1000.0
                _debug.record_cli_call(cmd, duration_ms, mode=mode, exit_code=typed[0])
                return typed
            outcome = _rpc_cli_run(endpoint, cmd, timeout)
            duration_ms = (time.perf_counter() - started) * 1000.0
            _debug.record_cli_call(cmd, duration_ms, mode=mode, exit_code=(outcome[0] if outcome is not None else None))
            return outcome
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        except (subprocess.TimeoutExpired, OSError) as exc:
            log.info("cli fetch failed", cmd=cmd[0], error=str(exc))
            duration_ms = (time.perf_counter() - started) * 1000.0
            _debug.record_cli_call(cmd, duration_ms, mode=mode, exit_code=1)
            return None
        duration_ms = (time.perf_counter() - started) * 1000.0
        _debug.record_cli_call(cmd, duration_ms, mode=mode, exit_code=result.returncode)
        return result.returncode, result.stdout, result.stderr
    except Exception:
        duration_ms = (time.perf_counter() - started) * 1000.0
        _debug.record_cli_call(cmd, duration_ms, mode=mode, exit_code=1)
        raise


def _cli_available(name: str) -> bool:
    """Whether a helper CLI (ghx, slackx) can run: on PATH, or served over rpc.

    In rpc mode the binary is not needed on this machine, so the configured
    server stands in for it; an unreachable server fails the call itself. A
    managed tool still needs its binary: this server runs it.
    """
    config = _rpc_config(name)
    if config is not None and config[0] == "rpc":
        return True
    return shutil.which(name) is not None


def _git(args: list[str], cwd: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _run_cli(cmd: list[str], timeout: int = 60) -> str | None:
    """Run a helper CLI, returning its stripped stdout when it exits 0."""
    outcome = _cli_run(cmd, timeout)
    if outcome is None or outcome[0] != 0:
        return None
    return outcome[1].strip()


def run_cli_raw(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str] | None:
    """Run a helper CLI and return the raw result, for callers that need stderr.

    In rpc mode a server problem comes back as a failed result whose stderr
    names it, so a diagnostics read shows the real cause instead of reading as
    "not installed".
    """
    outcome = _cli_run(cmd, timeout)
    if outcome is None:
        return None
    return subprocess.CompletedProcess(cmd, returncode=outcome[0], stdout=outcome[1], stderr=outcome[2])
