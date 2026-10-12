---
title: "Task tags"
status: draft
session_link: "http://localhost:10000/?session=ses_ed2936849ffePjqvp9kEDOH0mX"
---

# CLI Design: Task tags

## Design Principles

- Extends the existing `agentic` CLI conventions: cyclopts commands, `noun subcommand` grouping, long options only, and `--format {auto,json,text}` output (auto is json when stdout is not a TTY).
- The CLI is a thin client over the HTTP API; the tag filter maps directly to the `tag` query parameter so semantics match the API and the web UI (NFR-2).
- Read-only tag surface for now: tagging a task is done with the existing `task create --tags` / `task update --tags`, so only listing and filtering are new.

## Command Tree

```
agentic
├── task                    Create and manage tasks
│   ├── list                List tasks, newest first (filters: --status, --q, --tag)
│   ├── create              Create a task (--tags)
│   └── update              Update a task's fields (--tags)
└── tag                     Inspect the tags carried by tasks
    └── list                List the tags in use, with counts
```

## Commands

### `agentic task list`

**Description:** Lists tasks newest-first, optionally filtered by status, a text query, and one or more tags.
Serves FR-2 and FR-7.

**Synopsis:**

```
agentic task list [--status STATUS] [--q TEXT] [--tag TAG ...]
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| (none) | | The command takes no positional arguments |

**Options:**

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--status` | open \| in_progress \| blocked \| done \| archived | | Keep only tasks with this status |
| | `--q` | text | | Substring match over title, description, and summary |
| | `--tag` | tag (repeatable) | | Keep only tasks that carry every given tag |
| | `--format` | auto \| json \| text | auto | Output format |
| | `--api-url` | url | `$AGENTIC_API_URL` or `http://127.0.0.1:8600` | API base URL |
| | `--timeout` | seconds | 60 | Per-request timeout |

**Examples:**

```bash
agentic task list --tag bug
agentic task list --tag bug --tag ui --format json
```

**Errors:** an API error (for example a missing task) prints `error: ... (HTTP <status>)` to stderr and exits 1.

### `agentic tag list`

**Description:** Lists the tags in use, each with the number of tasks that carry it, most used first then alphabetically.
Serves FR-3 and FR-7.

**Synopsis:**

```
agentic tag list
```

**Options:**

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--format` | auto \| json \| text | auto | Output format |
| | `--api-url` | url | `$AGENTIC_API_URL` or `http://127.0.0.1:8600` | API base URL |
| | `--timeout` | seconds | 60 | Per-request timeout |

**Examples:**

```bash
agentic tag list
agentic tag list --format json
```

**Errors:** an API error (for example a missing task) prints `error: ... (HTTP <status>)` to stderr and exits 1.

### `agentic task create` / `agentic task update`

**Description:** Existing commands; `--tags` (repeatable) sets the full tag list on a task.
Serves FR-1, FR-6 (as the CLI path), and FR-8.

**Synopsis:**

```
agentic task create [--title TEXT] [--description TEXT] [--priority INT] [--status STATUS] [--tags TAG ...] [--github-url URL]
agentic task update TASK_ID [--title TEXT] [--status STATUS] [--priority INT] [--tags TAG ...] [--summary TEXT]
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `TASK_ID` | Yes (`task update` only) | The task to update |

**Options:**

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--tags` | tag (repeatable) | | The task's full tag list (replaces the stored list) |
| | `--title` | text | | Task title |
| | `--description` | text | | Task description |
| | `--status` | open \| in_progress \| blocked \| done \| archived | open (create) | Task status |
| | `--priority` | int (0-3) | 2 (create) | 0 low, 1 medium, 2 high, 3 urgent |
| | `--summary` | text | | Agent-maintained summary (update only) |
| | `--github-url` | url | | Import the task from a GitHub issue/PR (create only) |

**Examples:**

```bash
agentic task create --title "Fix flaky test" --tags bug --tags ci
agentic task update t1 --tags bug --tags urgent
```

**Errors:** updating or deleting an unknown task prints `error: Task not found (HTTP 404)` and exits 1.

## Global Options

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--api-url` | url | `$AGENTIC_API_URL` or `http://127.0.0.1:8600` | API base URL |
| | `--format` | auto \| json \| text | auto | Output format (`auto` is json when stdout is not a TTY) |
| | `--timeout` | seconds | 60 | Per-request timeout |
| | `--help` | | | Show help and exit |

## Environment Variables

| Variable | Used by | Default | Description |
|---|---|---|---|
| `AGENTIC_API_URL` | all | `http://127.0.0.1:8600` | API base URL |
| `AGENTIC_FORMAT` | all | `auto` | Default output format |
| `AGENTIC_TIMEOUT` | all | `60` | Default request timeout |

## Configuration

- No config file; flags and environment variables only.
- Precedence: CLI flags > environment variables > defaults.

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Runtime failure (for example the API is unreachable or returns an error) |
| 130 | Interrupted (Ctrl-C) |

## Output Behavior

- **stdout:** the task rows (`<id>  [<status>] p<priority>  <title>  #tag #tag`) or the JSON payload.
- **stderr:** error messages only.
- **Machine-readable:** `--format json` (or piping) emits the full API objects (tasks, or `{name, count}` tag entries).
- **TTY behavior:** text output on a TTY, JSON when piped; output is not colorized or wrapped so piped JSON stays valid.

## Help Text

```
$ agentic tag --help
Usage: agentic tag COMMAND [OPTIONS]

Inspect the tags carried by tasks.

Commands
  list  List the tags in use, with how many tasks carry each.
```

## Error Messages

- Format: `error: <message> (HTTP <status>)` on stderr.
- Example: `error: Task not found (HTTP 404)`.

## Interactive Behavior

- **Prompts:** none; every command is non-interactive.
- **Destructive actions:** `task delete` removes a task and its children; it does not prompt (scriptable by design).
- **Dry run:** not applicable.

## Example Sessions

### List tasks by tag

```console
$ agentic task list --tag bug
8dcb9b08ca12  [open] p2  Fix flaky ingest test  #bug #ci
```

### List the tags in use

```console
$ agentic tag list
bug  (2)
ci  (1)
ui  (1)
$ agentic tag list --format json
[
  {"name": "bug", "count": 2},
  {"name": "ci", "count": 1},
  {"name": "ui", "count": 1}
]
```

### An unknown tag matches nothing

```console
$ agentic task list --tag nope
(none)
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
| FR-1 | `task create --tags`, `task update --tags` | The API normalizes the list on write |
| FR-2 | `task list --tag` | Repeatable; every tag must match |
| FR-3 | `tag list` | Returns `{name, count}`, most used first |
| FR-6 | `task create --tags` | CLI path for setting tags at creation |
| FR-7 | `task list --tag`, `tag list` | The CLI surface for filtering and enumeration |
| FR-8 | `task update --tags` | The API records the before/after on the timeline |

## Out of Scope

- A `tag rename` / `tag delete` command (per-task editing covers the current need).
- A `task list --tag` that matches any tag rather than all tags.

## Open Questions

1. Should `task list` gain a `--any-tag` variant, or should all tags always match?
