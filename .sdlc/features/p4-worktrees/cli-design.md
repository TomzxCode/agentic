---
title: "Worktrees"
status: draft
session_link: "http://localhost:10000/?session=ses_ed209e713ffe1UX3Qqhq0UZ7Tw"
---

# CLI Design: Worktrees

## Design Principles

- Extends the existing `agentic` CLI conventions: cyclopts commands, `noun subcommand` grouping, long options only, and `--format {auto,json,text}` output (auto is json when stdout is not a TTY).
- Every worktree command is scoped to a task (`TASK-ID` is the leading positional), because worktrees belong to tasks and the API nests them under `/api/tasks/{id}/worktrees`.
- The CLI is a thin client over the HTTP API; branch defaulting, path placement, and the git invocation are server-side, and a git failure surfaces as the API's 400 message verbatim (NFR-1).
- Removal is a soft delete: the web and CLI both keep the worktree row and its timeline event (FR-5).
- Destructive commands do not prompt: the CLI is scriptable by design (see Interactive Behavior).

## Command Tree

```
agentic
└── worktree                Create isolated git worktrees for tasks
    ├── list                List a task's worktrees
    ├── create              Create a worktree for a task
    └── remove              Remove a worktree from disk and stop tracking it
```

## Commands

### `agentic worktree list`

**Description:** Lists a task's worktrees, one row per worktree with its id, status, branch, and path.
Serves FR-4.

**Synopsis:**

```
agentic worktree list TASK_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `TASK_ID` | Yes | The task whose worktrees to list |

**Options:** the global options only.

**Examples:**

```bash
agentic worktree list 8dcb9b08ca12
agentic worktree list 8dcb9b08ca12 --format json
```

**Errors:** an unknown task prints `error: Task not found (HTTP 404)` and exits 1.

### `agentic worktree create`

**Description:** Creates a git worktree for a task from a registered repository.
When `--branch` is omitted the branch defaults to `agentic/<slug-of-title>-<task-id-prefix>`; when the branch already exists it is checked out, otherwise it is created from the repository's default branch or `--base`.
Serves FR-1, FR-2, and FR-3.

**Synopsis:**

```
agentic worktree create TASK_ID [--repository-id ID] [--branch BRANCH] [--base REF]
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `TASK_ID` | Yes | The task to create the worktree for |

**Options:**

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--repository-id` | id | the task's first repository | The repository to branch from |
| | `--branch` | text | `agentic/<slug>-<id4>` | The branch to check out or create |
| | `--base` | ref | the default branch | The base ref for a new branch |

**Examples:**

```bash
agentic worktree create 8dcb9b08ca12
agentic worktree create 8dcb9b08ca12 --branch fix/ingest --base main
```

**Errors:** a git failure prints the git error, for example `error: <git error> (HTTP 400)`, and exits 1 (NFR-1).

### `agentic worktree remove`

**Description:** Removes a worktree's directory from disk and marks the row removed, keeping the record and recording a timeline event.
Serves FR-5.

**Synopsis:**

```
agentic worktree remove TASK_ID WORKTREE_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `TASK_ID` | Yes | The task the worktree belongs to |
| `WORKTREE_ID` | Yes | The worktree to remove |

**Options:** the global options only.

**Examples:**

```bash
agentic worktree remove 8dcb9b08ca12 71f3c9
```

**Errors:** an unknown task or worktree prints `error: ... (HTTP 404)` and exits 1.

## Global Options

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--api-url` | url | `$AGENTIC_API_URL` or `http://127.0.0.1:8600` | API base URL |
| | `--format` | auto \| json \| text | auto | Output format (`auto` is json when stdout is not a TTY) |
| | `--timeout` | seconds | 60 | Per-request timeout |
| -h | `--help` | | | Show help and exit |
| | `--version` | | | Display application version |

## Environment Variables

| Variable | Used by | Default | Description |
|---|---|---|---|
| `AGENTIC_API_URL` | all | `http://127.0.0.1:8600` | API base URL |
| `AGENTIC_FORMAT` | all | `auto` | Default output format |
| `AGENTIC_TIMEOUT` | all | `60` | Default request timeout |
| `AGENTIC_WORKTREE_ROOT` | server (FR-3) | `~/.agentic/worktrees` | Root under which worktrees are placed; not read by the CLI |

The `AGENTIC_*` connection variables are the documented defaults (FEAT-p6 FR-3), but the current launcher does not yet honor them (see FEAT-p6 Open Question 2).

## Configuration

- No config file; flags and environment variables only.
- Precedence: CLI flags > environment variables > defaults.

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Runtime failure (the API returns an error, the request fails, or git rejects the operation) |
| 2 | Usage error (unknown option or missing argument) |
| 130 | Interrupted (Ctrl-C) |

## Output Behavior

- **stdout:** worktree rows (`<id>  [<status>] <branch>  <path>`), the `created`/`removed` confirmation, or the JSON payload.
- **stderr:** error messages only.
- **Machine-readable:** `--format json` (or piping) emits the full API objects.
- **TTY behavior:** text on a TTY, JSON when piped; no color and no wrapping.

## Help Text

```
$ agentic worktree --help
Usage: agentic worktree COMMAND [OPTIONS]

Create isolated git worktrees for tasks.

Commands
  create  Create a worktree for a task.
  list    List a task's worktrees.
  remove  Remove a worktree from disk and stop tracking it.
```

## Error Messages

- Format: `error: <message> (HTTP <status>)` on stderr for API errors, which exit 1; a git failure carries git's own message.
- Usage errors print the parser's Rich error panel (for example `Unknown option: --bogus.`) and exit 2.
- Examples: `error: Task not found (HTTP 404)`, `error: fatal: a branch named 'fix/ingest' already exists (HTTP 400)`.

## Interactive Behavior

- **Prompts:** none; every command is non-interactive.
- **Destructive actions:** `worktree remove` deletes the directory from disk and does not prompt (scriptable by design); the record is kept so history survives.
- **Dry run:** not offered.

## Example Sessions

### Create and list a worktree

```console
$ agentic worktree create 8dcb9b08ca12
created worktree 71f3c9  agentic/fix-the-flaky-ingest-test-8dcb  /home/user/.agentic/worktrees/8dcb9b08ca12/agentic-fix-the-flaky-ingest-test-8dcb
$ agentic worktree list 8dcb9b08ca12
71f3c9  [active] agentic/fix-the-flaky-ingest-test-8dcb  /home/user/.agentic/worktrees/8dcb9b08ca12/agentic-fix-the-flaky-ingest-test-8dcb
```

### Remove a worktree

```console
$ agentic worktree remove 8dcb9b08ca12 71f3c9
removed worktree 71f3c9
$ agentic worktree list 8dcb9b08ca12
71f3c9  [removed] agentic/fix-the-flaky-ingest-test-8dcb  /home/user/.agentic/worktrees/8dcb9b08ca12/agentic-fix-the-flaky-ingest-test-8dcb
```

### Error path

```console
$ agentic worktree create 8dcb9b08ca12 --branch fix/ingest
error: fatal: a branch named 'fix/ingest' already exists (HTTP 400)
$ echo $?
1
```

## Requirements Traceability

| Requirement | Command(s) / Option(s) | Notes |
|---|---|---|
| FR-1 | `worktree create`, `--repository-id` | Default branch is derived server-side when `--branch` is omitted |
| FR-2 | `worktree create --branch --base` | Existing branch is checked out; a new one is based on the default branch or `--base` |
| FR-3 | `worktree create` | The path under `AGENTIC_WORKTREE_ROOT/<task_id>/<slug>` is chosen server-side |
| FR-4 | `worktree list TASK_ID` | Listed per task |
| FR-5 | `worktree remove TASK_ID WORKTREE_ID` | Directory removed, row marked removed, timeline event recorded |
| NFR-1 | `worktree create` errors | A git failure surfaces as HTTP 400 with the git message, not a 500 |
| NFR-2 | (server) | Git commands run with timeouts server-side; not visible in the CLI surface |

## Out of Scope

- A `worktree prune` command for stale directories: removal is per worktree.
- Selecting a base branch interactively: `--base` is explicit.
- Any direct git invocation by the CLI: all git work happens server-side.

## Open Questions

1. Should `worktree create` default to the newest active worktree elsewhere, or should one always be created explicitly (mirrors requirements Open Question 1)?
2. Should `worktree remove` offer `--keep-branch` to leave the branch in the repository?
