---
title: "Task management and timeline"
status: draft
session_link: "http://localhost:10000/?session=ses_ed209e713ffe1UX3Qqhq0UZ7Tw"
---

# CLI Design: Task management and timeline

## Design Principles

- Extends the existing `agentic` CLI conventions: cyclopts commands, `noun subcommand` grouping, long options only, and `--format {auto,json,text}` output (auto is json when stdout is not a TTY).
- The CLI is a thin client over the HTTP API; every command maps to a task endpoint so semantics match the API and the web UI.
- Global options (`--api-url`, `--format`, `--timeout`) are declared once on the app meta launcher and accepted by every command.
- Destructive commands do not prompt: the CLI is scriptable by design, and the web UI is where the interactive confirmation lives (see Interactive Behavior).

## Command Tree

```
agentic
└── task                    Create and manage tasks
    ├── list                List tasks, newest first (filters: --status, --q, --tag)
    ├── get                 Show a task with its items, worktrees, runs, and timeline
    ├── create              Create a task, or import one from a GitHub issue (--github-url)
    ├── update              Update a task's fields
    ├── delete              Delete a task and everything attached to it
    └── timeline            Show a task's timeline
```

## Commands

### `agentic task list`

**Description:** Lists tasks most recently updated first, optionally filtered by status, a text query, and one or more tags.
Serves FR-2 and FR-7.

**Synopsis:**

```
agentic task list [--status STATUS] [--q TEXT] [--tag TAG ...]
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| (none required) | | The filters may also be given positionally in the order listed |

**Options:**

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--status` | open \| in_progress \| blocked \| done \| archived | | Keep only tasks with this status |
| | `--q` | text | | Substring match over title, description, and summary |
| | `--tag` | tag (repeatable) | | Keep only tasks that carry every given tag (from FEAT-p9) |
| | `--empty-tag` | | | Repeatable companion that clears previously collected tags |
| | `--format` | auto \| json \| text | auto | Output format |
| | `--api-url` | url | `$AGENTIC_API_URL` or `http://127.0.0.1:8600` | API base URL |
| | `--timeout` | seconds | 60 | Per-request timeout |

**Examples:**

```bash
agentic task list
agentic task list --status in_progress
agentic task list --q flaky --format json
```

**Errors:** the API returning an error prints `error: ... (HTTP <status>)` and exits 1; an unreachable API currently propagates the connection error (see FEAT-p6 Error Messages).

### `agentic task get`

**Description:** Returns one task with its associations, worktrees, most recent runs, context, and timeline.
Serves FR-3.

**Synopsis:**

```
agentic task get TASK_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `TASK_ID` | Yes | The task to show |

**Options:** the global options only.

**Examples:**

```bash
agentic task get 8dcb9b08ca12
```

**Errors:** an unknown task prints `error: Task not found (HTTP 404)` and exits 1.

### `agentic task create`

**Description:** Creates a task from flags, or imports one from a GitHub issue or pull request when `--github-url` is given (the title and description are prefilled, and the issue is linked as an item).
Serves FR-1, FR-5, and FR-7.

**Synopsis:**

```
agentic task create [--title TEXT] [--description TEXT] [--priority INT] [--status STATUS]
                    [--tags TAG ...] [--repository-ids ID ...] [--group-id ID]
                    [--harness-id ID] [--github-url URL]
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| (none required) | | The fields may also be given positionally in the order listed |

**Options:**

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--title` | text | `""` | Task title (required unless `--github-url` supplies one) |
| | `--description` | text | `""` | Task description |
| | `--priority` | int (0-3) | 2 | 0 low, 1 medium, 2 high, 3 urgent |
| | `--status` | open \| in_progress \| blocked \| done \| archived | open | Task status |
| | `--tags` | tag (repeatable) | | The task's tag list (from FEAT-p9) |
| | `--repository-ids` | id (repeatable) | | Repositories to associate (FR-5) |
| | `--group-id` | id | | The repository group whose checkouts are relevant |
| | `--harness-id` | id | | The default harness for the task's runs |
| | `--github-url` | url | | Import and prefill from a GitHub issue or PR |

**Examples:**

```bash
agentic task create --title "Fix the flaky ingest test"
agentic task create --github-url https://github.com/o/r/issues/42
agentic task create --title "Ship tags" --status in_progress --priority 3 --tags ui
```

**Errors:** a missing title and `--github-url` prints `error: ... (HTTP 400)` and exits 1.

### `agentic task update`

**Description:** Updates a task's fields and records the changed fields with their before and after values in the timeline.
Serves FR-4, FR-5, and FR-7.

**Synopsis:**

```
agentic task update TASK_ID [--title TEXT] [--description TEXT] [--status STATUS] [--priority INT]
                    [--tags TAG ...] [--repository-ids ID ...] [--harness-id ID] [--summary TEXT]
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `TASK_ID` | Yes | The task to update |

**Options:**

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--title` | text | | Task title |
| | `--description` | text | | Task description |
| | `--status` | open \| in_progress \| blocked \| done \| archived | | Task status |
| | `--priority` | int (0-3) | | Task priority |
| | `--tags` | tag (repeatable) | | The task's full tag list (replaces the stored list) |
| | `--repository-ids` | id (repeatable) | | The task's full repository set (replaces the stored set) |
| | `--harness-id` | id | | The task's default harness |
| | `--summary` | text | | Agent-maintained summary |

**Examples:**

```bash
agentic task update 8dcb9b08ca12 --status done
agentic task update 8dcb9b08ca12 --priority 3 --tags urgent --tags bug
```

**Errors:** an unknown task prints `error: Task not found (HTTP 404)` and exits 1.

### `agentic task delete`

**Description:** Deletes a task and all of its child rows in foreign-key order, removing its worktrees from disk first.
Serves FR-6.

**Synopsis:**

```
agentic task delete TASK_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `TASK_ID` | Yes | The task to delete |

**Options:** the global options only.

**Examples:**

```bash
agentic task delete 8dcb9b08ca12
```

**Errors:** an unknown task prints `error: Task not found (HTTP 404)` and exits 1.

### `agentic task timeline`

**Description:** Prints a task's timeline, one line per event, newest first.
Serves FR-3 and FR-7 (the read side of the event log the other commands write).

**Synopsis:**

```
agentic task timeline TASK_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `TASK_ID` | Yes | The task whose timeline to print |

**Options:** the global options only.

**Examples:**

```bash
agentic task timeline 8dcb9b08ca12
agentic task timeline 8dcb9b08ca12 --format json
```

**Errors:** an unknown task prints `error: Task not found (HTTP 404)` and exits 1.

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

The `AGENTIC_*` variables are the documented defaults (FEAT-p6 FR-3), but the current launcher does not yet honor them (see FEAT-p6 Open Question 2).

## Configuration

- No config file; flags and environment variables only.
- Precedence: CLI flags > environment variables > defaults.

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Runtime failure (the API returns an error, or the request fails) |
| 2 | Usage error (unknown option or missing argument) |
| 130 | Interrupted (Ctrl-C) |

## Output Behavior

- **stdout:** the task rows (`<id>  [<status>] p<priority>  <title>  #tag #tag`), the task detail block, or the JSON payload.
- **stderr:** error messages only.
- **Machine-readable:** `--format json` (or piping) emits the full API objects.
- **TTY behavior:** text output on a TTY, JSON when piped; output is not colorized or wrapped so piped JSON stays valid.

## Help Text

```
$ agentic task --help
Usage: agentic task COMMAND [OPTIONS]

Create and manage tasks.

Commands
  create    Create a task (or import one from a GitHub issue with --github-url).
  delete    Delete a task and everything attached to it.
  get       Show a task with its items, worktrees, runs, and timeline.
  list      List tasks, newest first (optionally filtered by --tag, repeatable).
  timeline  Show a task's timeline.
  update    Update a task's fields.
```

## Error Messages

- Format: `error: <message> (HTTP <status>)` on stderr for API errors, which exit 1.
- Usage errors print the parser's Rich error panel (for example `Unknown option: --bogus.`) and exit 2.
- Example: `error: Task not found (HTTP 404)`.

## Interactive Behavior

- **Prompts:** none; every command is non-interactive.
- **Destructive actions:** `task delete` removes a task and its children and does not prompt (scriptable by design).
- **Dry run:** not applicable.

## Example Sessions

### Create, list, and read a task

```console
$ agentic task create --title "Fix the flaky ingest test"
created 8dcb9b08ca12  Fix the flaky ingest test
$ agentic task list
8dcb9b08ca12  [open] p2  Fix the flaky ingest test
$ agentic task get 8dcb9b08ca12
8dcb9b08ca12  [open] p2  Fix the flaky ingest test
  summary: The ingest test fails intermittently on CI.
  [ ] Reproduce with the seed CI uses
```

### Update a task and read the timeline

```console
$ agentic task update 8dcb9b08ca12 --status done
updated 8dcb9b08ca12  8dcb9b08ca12  [done] p2  Fix the flaky ingest test
$ agentic task timeline 8dcb9b08ca12
2026-10-12T15:20:47  updated            Updated: status
2026-10-12T14:03:11  created            Task created: Fix the flaky ingest test
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
| FR-1 | `task create` | Title, description, status, priority, tags, repositories, group, harness, or `--github-url` import |
| FR-2 | `task list --status --q` | Most recently updated first, with status and substring filters |
| FR-3 | `task get`, `task timeline` | Detail includes associations, worktrees, recent runs, and timeline |
| FR-4 | `task update` | The API records before/after values on the timeline |
| FR-5 | `task create/update --repository-ids` | Associates the repository set; the API records the timeline event |
| FR-6 | `task delete` | Removes children in foreign-key order and worktrees from disk |
| FR-7 | `task timeline` | Reads the event log the other commands write |
| FR-8 | (none) | The task SSE stream has no CLI consumer; it serves the web UI |

## Out of Scope

- A `task archive` shortcut: `task update --status archived` covers it.
- Group management (`--group-id` selects a group; creating groups is FEAT-p3's surface).
- Consuming the task SSE stream from the CLI (FR-8); the CLI reads state on demand.

## Open Questions

1. Should `task list` gain a `--limit` or pagination option, given the API returns the full list?
2. Should `task delete` gain a `--yes` flag if a confirmation prompt is ever added, or stay prompt-free like the rest of the client?
