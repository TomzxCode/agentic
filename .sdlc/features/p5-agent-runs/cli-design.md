---
title: "Agent runs and context refresh"
status: draft
session_link: "http://localhost:10000/?session=ses_ed209e713ffe1UX3Qqhq0UZ7Tw"
---

# CLI Design: Agent runs and context refresh

## Design Principles

- Extends the existing `agentic` CLI conventions: cyclopts commands, `noun subcommand` grouping, long options only, and `--format {auto,json,text}` output (auto is json when stdout is not a TTY).
- Long-running work is explicit: `run create` starts a run and returns immediately, `run wait` blocks until a terminal status, and `run stream` follows the live SSE event stream.
- The working directory is resolved server-side (explicit path, worktree, newest active worktree, first task repository, worktree root); `--cwd` and `--worktree-id` only pin an earlier choice.
- The CLI is a thin client over the HTTP API; ACP transport, event normalization, persistence, and cancellation all live in the backend.
- Cancelling a run is not a destructive delete and does not prompt: it stops work the user can restart.

## Command Tree

```
agentic
├── run                     Start, watch, and inspect agent runs
│   ├── list                List a task's agent runs
│   ├── get                 Show a run, including its session links
│   ├── events              Show a run's transcript
│   ├── create              Start an agent run against a task
│   ├── cancel              Cancel a running agent
│   ├── wait                Block until a run finishes, then print it
│   └── stream              Stream a run's events live (json lines or plain text)
├── context                 Read or refresh a task's agent-maintained context
│   ├── get                 Show a task's current summary and next steps
│   └── refresh             Ask an agent to rewrite the summary and next steps
├── harness                 Inspect and configure agent harnesses
│   ├── list                List harnesses and whether they are on PATH
│   ├── create              Add an ACP harness
│   ├── update              Update a harness
│   └── delete              Delete a harness
└── settings                Read and update app settings
    ├── get                 Show effective settings and their overrides
    └── set                 Override session-link settings
```

## Commands

### `agentic run list`

**Description:** Lists a task's agent runs, one row per run with its id, status, kind, and prompt.
Serves FR-3 (read side) and FR-4.

**Synopsis:**

```
agentic run list TASK_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `TASK_ID` | Yes | The task whose runs to list |

**Options:** the global options only.

**Examples:**

```bash
agentic run list 8dcb9b08ca12
```

**Errors:** an unknown task prints `error: Task not found (HTTP 404)` and exits 1.

### `agentic run get`

**Description:** Returns one run with its status, kind, prompt, working directory, and session links (an OpenChamber URL, a terminal URL, and a copyable resume command).
Serves FR-7.

**Synopsis:**

```
agentic run get RUN_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `RUN_ID` | Yes | The run to show |

**Options:** the global options only.

**Examples:**

```bash
agentic run get 4c1e77
agentic run get 4c1e77 --format json
```

**Errors:** an unknown run prints `error: ... (HTTP 404)` and exits 1.

### `agentic run events`

**Description:** Prints a run's persisted transcript, one `[<type>] <text>` line per event.
Serves FR-4.

**Synopsis:**

```
agentic run events RUN_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `RUN_ID` | Yes | The run whose events to print |

**Options:** the global options only.

**Examples:**

```bash
agentic run events 4c1e77
agentic run events 4c1e77 --format json
```

**Errors:** an unknown run prints `error: ... (HTTP 404)` and exits 1.

### `agentic run create`

**Description:** Starts an agent run against a task, resolving the working directory when `--cwd` and `--worktree-id` are omitted, and returns the created run immediately.
Serves FR-3.

**Synopsis:**

```
agentic run create TASK_ID PROMPT [--harness-id ID] [--worktree-id ID] [--cwd PATH]
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `TASK_ID` | Yes | The task to run against |
| `PROMPT` | Yes | The prompt for the agent |

**Options:**

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--harness-id` | id | the task's or default harness | The harness to run |
| | `--worktree-id` | id | newest active worktree | The worktree to run in |
| | `--cwd` | path | resolved server-side | An explicit working directory |

The working directory falls back in order: `--cwd`, `--worktree-id`, the newest active worktree, the first task repository, the worktree root.

**Examples:**

```bash
agentic run create 8dcb9b08ca12 "Investigate the failure"
agentic run create 8dcb9b08ca12 "Run the tests" --harness-id pi --cwd ~/src/app
```

**Errors:** an unknown task or harness prints `error: ... (HTTP 404)` and exits 1.

### `agentic run cancel`

**Description:** Cancels a running agent run.
Serves FR-5.

**Synopsis:**

```
agentic run cancel RUN_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `RUN_ID` | Yes | The run to cancel |

**Options:** the global options only.

**Examples:**

```bash
agentic run cancel 4c1e77
```

**Errors:** an unknown run prints `error: ... (HTTP 404)` and exits 1.

### `agentic run wait`

**Description:** Polls a run until it reaches a terminal status (`succeeded`, `failed`, or `cancelled`) or the wait budget elapses, then prints the run.
Serves FR-4 and p6-cli FR-5 (the blocking watch).

**Synopsis:**

```
agentic run wait RUN_ID [--timeout SECONDS] [--interval SECONDS]
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `RUN_ID` | Yes | The run to wait for |

**Options:**

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--timeout` | seconds | 600 | The wait budget; on expiry it prints the current status and exits 0 |
| | `--interval` | seconds | 2 | Poll interval |

`--timeout` here is the wait budget and shadows the global request timeout for this command (see Open Questions).

**Examples:**

```bash
agentic run wait 4c1e77
agentic run wait 4c1e77 --timeout 120 --interval 5
```

**Errors:** an unknown run prints `error: ... (HTTP 404)` and exits 1; a timeout is not an error (the run is printed with its current status).

### `agentic run stream`

**Description:** Follows a run's live SSE event stream, printing JSON lines on a pipe or `[<type>] <text>` lines on a TTY, and stops at `run_finished`.
Serves FR-4.

**Synopsis:**

```
agentic run stream RUN_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `RUN_ID` | Yes | The run whose stream to follow |

**Options:** the global options only.

**Examples:**

```bash
agentic run stream 4c1e77
agentic run stream 4c1e77 | jq -c 'select(.type=="message")'
```

**Errors:** an unknown run prints `error: ... (HTTP 404)` and exits 1; Ctrl-C exits 130.

### `agentic context get`

**Description:** Prints a task's current agent-maintained summary and next steps.
Serves FR-6 (read side).

**Synopsis:**

```
agentic context get TASK_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `TASK_ID` | Yes | The task whose context to show |

**Options:** the global options only.

**Examples:**

```bash
agentic context get 8dcb9b08ca12
```

**Errors:** an unknown task prints `error: Task not found (HTTP 404)` and exits 1.

### `agentic context refresh`

**Description:** Starts a context-refresh run that builds a prompt from the task and its items, runs it, and stores the parsed `{summary, next_steps}`.
Serves FR-6.

**Synopsis:**

```
agentic context refresh TASK_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `TASK_ID` | Yes | The task to refresh |

**Options:** the global options only.

**Examples:**

```bash
agentic context refresh 8dcb9b08ca12
```

**Errors:** an unknown task prints `error: Task not found (HTTP 404)` and exits 1; the refresh run fails asynchronously (watch it with `run wait`).

### `agentic harness list`

**Description:** Lists harnesses, whether each command is available on `PATH`, and which is the default (marked with a leading `*`).
Serves FR-1.

**Synopsis:**

```
agentic harness list
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| (none) | | The command takes no arguments |

**Options:** the global options only.

**Examples:**

```bash
agentic harness list
agentic harness list --format json
```

**Errors:** the API returning an error prints `error: ... (HTTP <status>)` and exits 1; an unreachable API currently propagates the connection error (see FEAT-p6 Error Messages).

### `agentic harness create`

**Description:** Adds an ACP harness with its command, arguments, description, resume command, and model.
Serves FR-2.

**Synopsis:**

```
agentic harness create NAME COMMAND [--args ARG ...] [--description TEXT]
                      [--resume-command TEMPLATE] [--model MODEL]
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `NAME` | Yes | The harness name |
| `COMMAND` | Yes | The ACP command to run (for example `opencode`) |

**Options:**

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--args` | arg (repeatable) | `[]` | Arguments passed to the command |
| | `--description` | text | `""` | A description |
| | `--resume-command` | template | | The command to resume the harness's session |
| | `--model` | model | | The default model |

**Examples:**

```bash
agentic harness create opencode opencode --args acp
agentic harness create pi pi-acp --resume-command "pi --session {session}"
```

**Errors:** an invalid harness prints `error: ... (HTTP <status>)` and exits 1.

### `agentic harness update`

**Description:** Updates a harness's fields.
Serves FR-2.

**Synopsis:**

```
agentic harness update HARNESS_ID [--name NAME] [--command COMMAND] [--args ARG ...]
                      [--resume-command TEMPLATE] [--model MODEL]
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `HARNESS_ID` | Yes | The harness to update |

**Options:** `--name`, `--command`, `--args`, `--resume-command`, and `--model`, all optional.
Unlike `harness create`, `harness update` has no `--description` option.

**Examples:**

```bash
agentic harness update opencode --args acp --model gpt-5
```

**Errors:** an unknown harness prints `error: ... (HTTP 404)` and exits 1.

### `agentic harness delete`

**Description:** Deletes a harness.
Serves FR-2.

**Synopsis:**

```
agentic harness delete HARNESS_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `HARNESS_ID` | Yes | The harness to delete |

**Options:** the global options only.

**Examples:**

```bash
agentic harness delete opencode
```

**Errors:** an unknown harness prints `error: ... (HTTP 404)` and exits 1.

### `agentic settings get` / `agentic settings set`

**Description:** Reads effective settings and their stored overrides, and overrides the session-link settings (an empty string disables a link).
Serves FR-7 and FR-8.

**Synopsis:**

```
agentic settings get
agentic settings set [--openchamber-url URL] [--openchamber-session-path PATH] [--terminal-url-template TEMPLATE]
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| (none required) | | The fields may also be given positionally in the order listed |

**Options:**

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--openchamber-url` | url | | The OpenChamber base URL |
| | `--openchamber-session-path` | path | | The session path appended to the base (for example `/?session={session}`) |
| | `--terminal-url-template` | template | | The terminal URL template; empty disables the link |

Stored overrides win over environment defaults (FR-8).

**Examples:**

```bash
agentic settings get
agentic settings set --openchamber-url http://localhost:10000 --openchamber-session-path "/?session={session}"
agentic settings set --terminal-url-template ""
```

**Errors:** the API returning an error prints `error: ... (HTTP <status>)` and exits 1; an unreachable API currently propagates the connection error (see FEAT-p6 Error Messages).

## Global Options

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--api-url` | url | `$AGENTIC_API_URL` or `http://127.0.0.1:8600` | API base URL |
| | `--format` | auto \| json \| text | auto | Output format (`auto` is json when stdout is not a TTY) |
| | `--timeout` | seconds | 60 | Per-request timeout (shadowed by `run wait --timeout`) |
| -h | `--help` | | | Show help and exit |
| | `--version` | | | Display application version |

## Environment Variables

| Variable | Used by | Default | Description |
|---|---|---|---|
| `AGENTIC_API_URL` | all | `http://127.0.0.1:8600` | API base URL |
| `AGENTIC_FORMAT` | all | `auto` | Default output format |
| `AGENTIC_TIMEOUT` | all | `60` | Default request timeout |
| `AGENTIC_OPENCHAMBER_URL` | server (FR-7) | (unset) | Session-link default overridden by `settings set` |
| `AGENTIC_TERMINAL_URL_TEMPLATE` | server (FR-7) | (unset) | Session-link default overridden by `settings set` |

The `AGENTIC_*` connection variables are the documented defaults (FEAT-p6 FR-3), but the current launcher does not yet honor them (see FEAT-p6 Open Question 2).

## Configuration

- Session-link settings are stored in the server's `setting` table and overridden with `settings set`; they are not a local CLI config file.
- Precedence for session links: stored overrides > environment defaults.
- Precedence for the CLI connection: flags > environment variables > defaults.

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success, including `run wait` reaching its budget |
| 1 | Runtime failure (the API returns an error, or the request fails) |
| 2 | Usage error (unknown option or missing argument) |
| 130 | Interrupted (Ctrl-C), for example during `run stream` |

## Output Behavior

- **stdout:** run rows (`<id>  <status>  <kind>  <prompt>`), the run detail block with session links, `[<type>] <text>` transcript lines, the context summary and next steps, harness rows, settings, and JSON lines from `run stream`.
- **stderr:** error messages only.
- **Machine-readable:** `--format json` (or piping) emits the full API objects; `run stream` emits one JSON object per line.
- **TTY behavior:** text on a TTY, JSON when piped; no color and no wrapping so piped JSON and JSON lines stay valid.

## Help Text

```
$ agentic run --help
Usage: agentic run COMMAND [OPTIONS]

Start, watch, and inspect agent runs.

Commands
  cancel  Cancel a running agent.
  create  Start an agent run against a task.
  events  Show a run's transcript.
  get     Show a run, including its session links.
  list    List a task's agent runs.
  stream  Stream a run's events live (json lines or plain text).
  wait    Block until a run finishes, then print it.
```

## Error Messages

- Format: `error: <message> (HTTP <status>)` on stderr for API errors, which exit 1.
- Usage errors print the parser's Rich error panel (for example `Unknown option: --bogus.`) and exit 2.
- Examples: `error: Task not found (HTTP 404)`, `error: Harness not found (HTTP 404)`.

## Interactive Behavior

- **Prompts:** none; every command is non-interactive.
- **Long-running:** `run create` returns immediately; `run wait` blocks to a terminal status or its budget; `run stream` follows until `run_finished` or Ctrl-C.
- **Destructive actions:** `harness delete` does not prompt (scriptable by design); `run cancel` stops work rather than deleting it.
- **Dry run:** not offered.

## Example Sessions

### Start a run and watch it

```console
$ agentic run create 8dcb9b08ca12 "Investigate the flaky test"
started run 4c1e77 (running) in /home/user/.agentic/worktrees/8dcb9b08ca12/agentic-fix-the-flaky-ingest-test-8dcb
$ agentic run stream 4c1e77
[message] Looking at the ingest test...
[tool_call] grep -n "sleep" tests/test_ingest.py
[message] Found a 5s sleep that races with the timeout.
[run_finished] Run finished
```

### Wait for a run and read its links

```console
$ agentic run wait 4c1e77 --timeout 120
4c1e77  succeeded  run             Investigate the flaky test
  session: ses_abc123
  cwd: /home/user/.agentic/worktrees/8dcb9b08ca12/agentic-fix-the-flaky-ingest-test-8dcb
  openchamber: http://localhost:10000/?session=ses_abc123
  resume: pi --session ses_abc123
```

### Refresh context and read it

```console
$ agentic context refresh 8dcb9b08ca12
context refresh started: run 9a3f21
$ agentic context get 8dcb9b08ca12
The ingest test fails intermittently under CI load.
- [ ] Reproduce with the seed CI uses
```

### Error path

```console
$ agentic run get does-not-exist
error: Run not found (HTTP 404)
$ echo $?
1
```

## Requirements Traceability

| Requirement | Command(s) / Option(s) | Notes |
|---|---|---|
| FR-1 | `harness list` | Reports each seeded harness and whether it is on `PATH` |
| FR-2 | `harness create`, `harness update`, `harness delete`, `harness list` | Command, args, resume command, and model; `env` and a default flag are not exposed (see Open Questions) |
| FR-3 | `run create --harness-id --worktree-id --cwd` | Working directory resolved server-side when the flags are omitted |
| FR-4 | `run create`, `run events`, `run stream` | Events persisted and streamed over SSE; `run stream` follows the stream |
| FR-5 | `run cancel`, `run wait` | Cancellation, and blocking until a terminal status |
| FR-6 | `context get`, `context refresh` | Builds the prompt, runs it, stores the parsed summary and next steps |
| FR-7 | `run get`, `settings get` | OpenChamber URL, terminal URL, and resume command per run |
| FR-8 | `settings get`, `settings set` | Stored overrides win over environment defaults |
| NFR-1 | `run get`, `run wait` | A failed run is a terminal `failed` status, not a crash |
| NFR-2 | (server) | The harness process is terminated server-side after a turn; not visible in the CLI |
| NFR-3 | `run stream` | Streaming stays responsive because blocking work runs off the event loop |
| NFR-4 | (server) | Permission requests are auto-approved server-side |

## Out of Scope

- An interactive TUI or prompt permission approval (requirements Open Question 1); permissions are auto-approved.
- Scheduling a context refresh after a run completes (requirements Open Question 2); refresh is explicit.
- `harness --env` and a `--default` flag on `harness create`: not exposed by the CLI today.
- A single `run create --wait` flag: waiting is the separate `run wait` command (see p6-cli Open Question 1).

## Open Questions

1. Should `harness create`/`harness update` expose `--env` and a `--default` flag to match the API's harness fields?
2. Should `run wait --timeout` be renamed `--wait-timeout` so it does not shadow the global `--timeout`?
3. Should `run stream` grow a `--json` alias or document that piping already selects JSON lines?
