---
title: "Create a task from a Slack thread"
status: done
session_link: "http://localhost:10000/?session=ses_ecf740bfcffeTbPo9DIeiSPyDH"
---

# CLI Design: Create a task from a Slack thread

## Design Principles

- Extends the existing `agentic` CLI conventions: cyclopts commands, `noun subcommand` grouping, long options only, and `--format {auto,json,text}` output.
- The CLI is a thin client over the HTTP API; `--slack-url` maps directly to the `slack_url` field on `POST /api/tasks`.
- The command stays non-interactive: it creates the task and returns; the agent names and summarizes it in the background, as the web UI does.

## Command Tree

```
agentic
└── task                    Create and manage tasks
    └── create              Create a task (--github-url, --slack-url)
```

## Commands

### `agentic task create`

**Description:** Creates a task from a title, or imports one from a GitHub issue/PR (`--github-url`) or a Slack thread (`--slack-url`).
With `--slack-url`, the API fetches the thread, associates it, and dispatches a background agent run that names the task and summarizes the discussion; the command returns the task as soon as it is created.
Serves FR-6.

**Synopsis:**

```
agentic task create [--title TEXT] [--description TEXT] [--priority INT] [--status STATUS] [--tags TAG ...] [--repository-ids ID ...] [--group-id ID] [--harness-id ID] [--github-url URL] [--slack-url URL]
```

**Options:**

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--title` | text | | Task title (optional when importing) |
| | `--description` | text | | Task description |
| | `--status` | open \| in_progress \| blocked \| done \| archived | open | Task status |
| | `--priority` | int (0-3) | 2 | 0 low, 1 medium, 2 high, 3 urgent |
| | `--tags` | tag (repeatable) | | The task's tag list |
| | `--repository-ids` | id (repeatable) | | Repositories to associate |
| | `--group-id` | id | | Repository group |
| | `--harness-id` | id | | Harness for agent runs |
| | `--github-url` | url | | Import the task from a GitHub issue/PR |
| | `--slack-url` | url | | Import the task from a Slack thread (an agent names and summarizes it) |

**Examples:**

```bash
agentic task create --slack-url https://acme.slack.com/archives/C123/p1700000000000000
agentic task create --slack-url https://acme.slack.com/archives/C123/p1700000000000000 --tags bug
agentic task create --title "My title" --slack-url https://acme.slack.com/archives/C123/p1700000000000000
```

**Errors:** if neither a title nor an import URL is given, the API returns `error: Title is required (or provide a github_url or slack_url) (HTTP 400)` and the command exits 1.
An unauthenticated `slackx` does not fail the command; the task is created with a placeholder title.

## Global Options

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--api-url` | url | `$AGENTIC_API_URL` or `http://127.0.0.1:8600` | API base URL |
| | `--format` | auto \| json \| text | auto | Output format (`auto` is json when stdout is not a TTY) |
| | `--timeout` | seconds | 60 | Per-request timeout |
| | `--help` | | | Show help and exit |

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Runtime failure (for example the API is unreachable or returns an error) |
| 130 | Interrupted (Ctrl-C) |

## Output Behavior

- **stdout:** `created <id>  <title>` in text mode, or the full `TaskRead` JSON.
- **stderr:** error messages only.
- **Machine-readable:** `--format json` (or piping) emits the created task, including the title (the placeholder, until the background run writes the agent's title).

## Example Sessions

### Create from a Slack thread

```console
$ agentic task create --slack-url https://acme.slack.com/archives/C123/p1700000000000000
created 8dcb9b08ca12  Slack thread
$ agentic task create --slack-url https://acme.slack.com/archives/C123/p1700000000000000 --format json | jq '{id, title}'
{
  "id": "8dcb9b08ca12",
  "title": "Slack thread"
}
```

### Error path

```console
$ agentic task create
error: Title is required (or provide a github_url or slack_url) (HTTP 400)
$ echo $?
1
```

## Requirements Traceability

| Requirement | Command(s) / Option(s) | Notes |
|---|---|---|
| FR-6 | `task create --slack-url` | Forwarded as `slack_url` on `POST /api/tasks` |
| FR-3 | `task create --title`, `task create --slack-url` | A supplied title is kept; otherwise the agent's title is written |

## Out of Scope

- A `task import` command separate from `task create`.
- Waiting for (or streaming) the summary run from the CLI; the run is visible through `run list` / `run stream`.

## Open Questions

1. Should `task create --slack-url` gain a `--wait` flag that blocks until the title and summary are written?
