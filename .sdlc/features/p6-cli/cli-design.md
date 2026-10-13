---
title: "Command-line interface"
status: draft
session_link: "http://localhost:10000/?session=ses_ed209e713ffe1UX3Qqhq0UZ7Tw"
---

# CLI Design: Command-line interface

This is the umbrella design for the `agentic` and `agentic-server` commands: the command tree, the global options, and the cross-command behavior every group inherits.
Per-command detail lives in the feature that owns each group (`task` in FEAT-p1, `item`/`link` in FEAT-p2, `repository` in FEAT-p3, `worktree` in FEAT-p4, `run`/`context`/`harness`/`settings` in FEAT-p5, `tag` in FEAT-p9).

## Design Principles

- Framework: cyclopts, with grouped subcommands under a noun (`task`, `item`, `run`, ...) and verb subcommands under each group.
- Two commands, two packages: `agentic` (the `agentic-cli` package) is the user client over HTTP; `agentic-server` (the backend package) runs and inspects the server. The client never imports the backend.
- The client is a thin layer over the HTTP API (NFR-2): it passes JSON through and renders it; it never touches the database.
- Global options live once on the app meta launcher and are accepted by every command.
- Output is never wrapped and markup is never interpreted, so piped JSON stays valid and `[open]`-style text stays literal (NFR-1).
- Every group is discoverable from `agentic --help` (NFR-3).
- Destructive commands do not prompt: the CLI is scriptable by design, and the web UI is where interactive confirmation lives.

## Command Tree

```
agentic
├── health                  Check that the API is reachable
├── task                    Create and manage tasks
├── tag                     Inspect the tags carried by tasks
├── item                    Create and manage source items
├── link                    Associate items with tasks
├── repository              Register local git repositories
├── worktree                Create isolated git worktrees for tasks
├── run                     Start, watch, and inspect agent runs
├── context                 Read or refresh a task's agent-maintained context
├── harness                 Inspect and configure agent harnesses
└── settings                Read and update app settings

agentic-server
├── serve                   Run the Agentic API server (and serve the built SPA if present)
└── info                    Print backend configuration, database location, and harness availability
```

`agentic-server` with no subcommand defaults to `serve`.

## Commands

### `agentic health`

**Description:** Calls `GET /api/health` and reports the service status and the API URL it reached.
Serves FR-1 (the health resource).

**Synopsis:**

```
agentic health
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| (none) | | The command takes no arguments |

**Options:** the global options only.

**Examples:**

```bash
agentic health
```

**Errors:** the API returning an error prints `error: ... (HTTP <status>)` and exits 1; an unreachable API currently propagates the connection error (see Error Messages for the gap).

### `agentic <group> <subcommand>`

**Description:** The resource groups (FR-1): `task`, `tag`, `item`, `link`, `repository`, `worktree`, `run`, `context`, `harness`, `settings`.
Every group is a cyclopts `App` whose subcommands map one-to-one to API operations.
The per-command synopses, options, and examples are in the owning feature's `cli-design.md` (FEAT-p1, p2, p3, p4, p5, p9).

**Synopsis:**

```
agentic task|tag|item|link|repository|worktree|run|context|harness|settings COMMAND [OPTIONS]
```

**Examples:**

```bash
agentic task list
agentic run stream 4c1e77
```

**Errors:** every subcommand routes its API and usage errors through the shared handler (see Error Messages).

### `agentic-server serve`

**Description:** Runs the API server with uvicorn, and serves the built SPA when it is present.
Serves FR-4.

**Synopsis:**

```
agentic-server serve [--host HOST] [--port PORT] [--reload | --no-reload]
agentic-server [--host HOST] [--port PORT] [--reload | --no-reload]   # defaults to serve
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| (none required) | | `--host`, `--port`, and `--reload` are the only inputs |

**Options:**

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--host` | host | 127.0.0.1 | Bind address |
| | `--port` | port | 8600 | Bind port |
| | `--reload` / `--no-reload` | bool | no reload | Auto-reload on code changes |

**Examples:**

```bash
agentic-server
agentic-server serve --reload
agentic-server serve --host 0.0.0.0 --port 9000
```

**Errors:** a port already in use is reported by uvicorn on stderr and the process exits non-zero.

### `agentic-server info`

**Description:** Prints the backend configuration (data dir, database, worktree root, static dir), the default harness, and each harness's availability.
Serves FR-4.

**Synopsis:**

```
agentic-server info
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| (none) | | The command takes no arguments |

**Options:** none.

**Examples:**

```bash
agentic-server info
```

**Errors:** an unwritable data directory surfaces as a filesystem error on stderr and a non-zero exit.

## Global Options

`agentic` global options (declared once on the meta launcher, accepted by every command):

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--api-url` | url | `$AGENTIC_API_URL` or `http://127.0.0.1:8600` | API base URL |
| | `--format` | auto \| json \| text | auto | Output format (`auto` is json when stdout is not a TTY) |
| | `--timeout` | seconds | 60 | Per-request timeout (shadowed by `run wait --timeout`) |
| -h | `--help` | | | Show help and exit |
| | `--version` | | | Display application version |

`agentic-server` global options: `--host`, `--port`, `--reload`/`--no-reload`, `--help`, `--version`.

## Environment Variables

| Variable | Used by | Default | Description |
|---|---|---|---|
| `AGENTIC_API_URL` | `agentic` (all) | `http://127.0.0.1:8600` | API base URL |
| `AGENTIC_FORMAT` | `agentic` (all) | `auto` | Default output format |
| `AGENTIC_TIMEOUT` | `agentic` (all) | `60` | Default request timeout |

The `AGENTIC_*` variables are the documented defaults (FR-3), but the current launcher overwrites them with the flag defaults, so they are not yet honored (see Open Question 2).

`agentic-server` reads the backend's own configuration (data dir, database path, worktree root, fs root, default harness) from the environment; that configuration is documented with the backend, not here.

## Configuration

- No config file; the CLI takes flags and environment variables only.
- Precedence: CLI flags > environment variables > defaults (FR-3).
- The `AGENTIC_*` variables supply the default for their matching flag, so an explicit flag always wins.

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Runtime failure (the API returns an error, or the request fails) |
| 2 | Usage error (unknown option or missing argument) |
| 130 | Interrupted (Ctrl-C) |

## Output Behavior

- **stdout:** the command's data, rendered as text on a TTY and as JSON when piped or with `--format json`.
- **stderr:** error messages only.
- **Machine-readable:** `--format json` (or piping, which selects JSON automatically) emits the API's JSON; `run stream` emits one JSON object per line (FR-2).
- **TTY behavior:** the CLI prints through a plain Rich console with markup disabled and soft wrapping off, so `[open]`-style text stays literal and piped JSON is never wrapped (NFR-1).

## Help Text

```
$ agentic --help
Usage: agentic COMMAND [OPTIONS]

Drive the Agentic app (tasks, items, agents) from the command line.

Commands
  context      Read or refresh a task's agent-maintained context.
  harness      Inspect and configure agent harnesses.
  health       Check that the API is reachable.
  item         Create and manage source items (Slack/GitHub/Drive/URL/note).
  link         Associate items with tasks.
  repository   Register local git repositories.
  run          Start, watch, and inspect agent runs.
  settings     Read and update app settings.
  tag          Inspect the tags carried by tasks.
  task         Create and manage tasks.
  worktree     Create isolated git worktrees for tasks.
  --help (-h)  Display this message and exit.
  --version    Display application version.

Parameters
  --api-url STR    Base URL of the Agentic API (default: $AGENTIC_API_URL or 127.0.0.1:8600).
  --format CHOICE  Output format. auto uses json when stdout is not a terminal.
  --timeout FLOAT  Per-request timeout in seconds.
```

## Error Messages

- API errors: `error: <message> (HTTP <status>)` on stderr, exit 1 (FR-6).
- Example: `error: Task not found (HTTP 404)`.
- Usage errors: the parser prints a Rich error panel (for example `Unknown option: --bogus.`) and exits 2, with no `error:` prefix.
- Ctrl-C prints `interrupted` on stderr and exits 130 (FR-6).
- Known gap: an unreachable API currently raises an unhandled connection error (a traceback) instead of the one-line message FR-6 requires (see Open Question 3).

## Interactive Behavior

- **Prompts:** none; the whole surface is non-interactive and safe in scripts.
- **Long-running:** `run wait` blocks to a terminal status or its budget; `run stream` follows until `run_finished` or Ctrl-C.
- **Destructive actions:** `task delete`, `item delete`, `repository remove`, `worktree remove`, and `harness delete` do not prompt (scriptable by design).
- **Dry run:** not offered.

## Example Sessions

### JSON when piped, text on a TTY

```console
$ agentic task list
8dcb9b08ca12  [open] p2  Fix the flaky ingest test
$ agentic task list | jq -r '.[].id'
8dcb9b08ca12
```

### Bracketed text stays literal

```console
$ agentic task list
8dcb9b08ca12  [open] p2  Fix the flaky ingest test
```

### Backend configuration

```console
$ agentic-server info
data dir:     /home/user/.agentic
database:     /home/user/.agentic/agentic.db
worktrees:    /home/user/.agentic/worktrees
static dir:   /home/user/src/agentic/backend/static (built: True)
default harness: opencode2
harnesses:
 *ok  opencode2  opencode2
  ok  opencode   opencode
  ok  pi         pi-acp
```

### Error path

```console
$ agentic task get does-not-exist
error: Task not found (HTTP 404)
$ echo $?
1
```

## Requirements Traceability

| Requirement | Command(s) / Option(s) | Notes |
|---|---|---|
| FR-1 | `task`, `tag`, `item`, `link`, `repository`, `worktree`, `run`, `context`, `harness`, `settings`, `health` | One group per resource, discoverable from `agentic --help` (`tag` added by FEAT-p9) |
| FR-2 | `--format auto\|json\|text` | JSON when stdout is not a TTY or on `--format json`; text otherwise |
| FR-3 | `--api-url`, `--timeout` | Flag over default `http://127.0.0.1:8600`; the `AGENTIC_*` env fallbacks are documented but not yet honored (see Open Question 2) |
| FR-4 | `agentic-server serve`, `agentic-server info` | `--host`, `--port`, `--reload`, plus configuration and harness reporting |
| FR-5 | `run stream`, `run wait` | Live SSE streaming and a blocking wait |
| FR-6 | shared error handler, exit codes | One-line stderr message, non-zero exit, 130 on interrupt |
| NFR-1 | plain Rich console, `--format` | No markup interpretation and no wrapping; piped JSON stays valid |
| NFR-2 | client/server split | The client imports only `httpx`, never the backend or database |
| NFR-3 | `agentic --help` | Every group is listed with its one-line purpose |

## Out of Scope

- Shell completion (a recognized gap; cyclopts supports it but it is not wired).
- An interactive TUI.
- A generated client: the CLI surface can drift from the API (p6-cli specification Risk 2).
- Configuring the backend through the client CLI; `agentic-server` and the environment own backend configuration.

## Open Questions

1. Should `run create` gain a `--wait` flag, or keep waiting as the separate `run wait` command (mirrors p6-cli Open Question 1)?
2. Should the `AGENTIC_*` defaults be wired through cyclopts `env_var` so FR-3 holds, or is "flags only" the intended interface?
3. Should an unreachable API be caught and reported as `error: cannot reach the API at <url>` (FR-6), instead of propagating the connection error?
4. Should the usage-error panel print an `error:` prefix so every failure path looks the same?
