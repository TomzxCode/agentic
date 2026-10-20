---
title: "Source items, associations, and GitHub import"
status: draft
session_link: "http://localhost:10000/?session=ses_ed209e713ffe1UX3Qqhq0UZ7Tw"
---

# CLI Design: Source items, associations, and GitHub import

## Design Principles

- Extends the existing `agentic` CLI conventions: cyclopts commands, `noun subcommand` grouping, long options only, and `--format {auto,json,text}` output (auto is json when stdout is not a TTY).
- The CLI is a thin client over the HTTP API; item creation maps directly to `POST /api/items`, so source inference and deduplication behave the same as in the web UI.
- Source is inferred from the URL or text when `--source` is omitted, so the common case is a single `--url` or `--content`.
- Linking reuses the task-side endpoint (`POST /api/tasks/{id}/items`), so `link add` can attach an existing item or create and attach a new one in one call.
- Destructive commands do not prompt: the CLI is scriptable by design (see Interactive Behavior).

## Command Tree

```
agentic
├── item                    Create and manage source items (Slack/GitHub/Drive/URL/note)
│   ├── list                List items (filter: --source)
│   ├── get                 Show an item
│   ├── create              Create an item (source inferred; fetches unless --no-fetch)
│   ├── refresh             Re-fetch an item's metadata/content
│   ├── done                Mark a Slack conversation done
│   ├── reopen              Reopen a done Slack conversation
│   └── delete              Delete an item and its associations
├── link                    Associate items with tasks
│   ├── add                 Attach an existing item or a new one to a task
│   └── remove              Remove an item's association with a task
└── task create             Import a task from a GitHub issue or PR (--github-url)
```

## Commands

### `agentic item list`

**Description:** Lists items, optionally filtered by source.
Serves FR-6.
The API also supports a text query, but this command does not expose it yet (see Open Questions).

**Synopsis:**

```
agentic item list [--source SOURCE]
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| (none required) | | The source filter may also be given positionally |

**Options:**

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--source` | slack \| github \| gdrive \| url \| note \| commit \| file | (all) | Keep only items of this source |

**Examples:**

```bash
agentic item list
agentic item list --source github
```

**Errors:** the API returning an error prints `error: ... (HTTP <status>)` and exits 1; an unreachable API currently propagates the connection error (see FEAT-p6 Error Messages).

### `agentic item get`

**Description:** Returns one item, including the ids of the tasks it is linked to.
Serves FR-6 and FR-9 (the `task_ids` field).

**Synopsis:**

```
agentic item get ITEM_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `ITEM_ID` | Yes | The item to show |

**Options:** the global options only.

**Examples:**

```bash
agentic item get 5f2a1c
agentic item get 5f2a1c --format json
```

**Errors:** an unknown item prints `error: Item not found (HTTP 404)` and exits 1.

### `agentic item create`

**Description:** Creates an item, inferring source, kind, and external id from the URL or text when `--source` is omitted, and fetching the title and content unless `--no-fetch`.
Text that is not a URL is stored as a note's content rather than a link.
Serves FR-1, FR-2, FR-3, and FR-4.

**Synopsis:**

```
agentic item create [--source SOURCE] [--url URL] [--title TEXT] [--content TEXT]
                    [--external-id ID] [--fetch | --no-fetch]
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| (none required) | | The fields may also be given positionally in the order listed |

**Options:**

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--source` | slack \| github \| gdrive \| url \| note \| commit \| file | (inferred) | Override the inferred source |
| | `--url` | url | | The item's URL; a non-URL value is stored as note content |
| | `--title` | text | `""` | Item title |
| | `--content` | text | `""` | Item content |
| | `--external-id` | id | | The external id (for example `o/r#42`) |
| | `--fetch` / `--no-fetch` | bool | fetch on | Fetch the item's title and content on create |

**Examples:**

```bash
agentic item create --url https://github.com/o/r/issues/42
agentic item create --content "remember to rotate the token"
agentic item create --url https://acme.slack.com/archives/C1/p1700000000 --no-fetch
```

**Errors:** a failed fetch never fails the command (NFR-1): the item is still created, so the exit code is 0.

### `agentic item refresh`

**Description:** Re-fetches an item's title and content from its source.
Serves FR-4 and FR-6.

**Synopsis:**

```
agentic item refresh ITEM_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `ITEM_ID` | Yes | The item to refresh |

**Options:** the global options only.

**Examples:**

```bash
agentic item refresh 5f2a1c
```

**Errors:** an unknown item prints `error: Item not found (HTTP 404)` and exits 1; a fetch failure still returns the item.

### `agentic item done`

**Description:** Marks a Slack conversation done.
A message that arrives afterwards is flagged on the item as new activity, but the conversation stays done until it is reopened.
Serves FR-10.

**Synopsis:**

```
agentic item done ITEM_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `ITEM_ID` | Yes | The item to mark done |

**Options:** the global options only.

**Examples:**

```bash
agentic item done 5f2a1c
```

**Errors:** an unknown item prints `error: Item not found (HTTP 404)` and exits 1.

### `agentic item reopen`

**Description:** Reopens a Slack conversation that was marked done, clearing its done state and any new-message flag.
Serves FR-10.

**Synopsis:**

```
agentic item reopen ITEM_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `ITEM_ID` | Yes | The item to reopen |

**Options:** the global options only.

**Examples:**

```bash
agentic item reopen 5f2a1c
```

**Errors:** an unknown item prints `error: Item not found (HTTP 404)` and exits 1.

### `agentic item delete`

**Description:** Deletes an item and its task associations.
Serves FR-6.

**Synopsis:**

```
agentic item delete ITEM_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `ITEM_ID` | Yes | The item to delete |

**Options:** the global options only.

**Examples:**

```bash
agentic item delete 5f2a1c
```

**Errors:** an unknown item prints `error: Item not found (HTTP 404)` and exits 1.

### `agentic link add`

**Description:** Associates an existing item (`--item-id`) or a newly created item (`--url` or `--content`) with a task, with an optional note.
Serves FR-5 and FR-7 (as the manual linking path).

**Synopsis:**

```
agentic link add TASK_ID [--item-id ID | --url URL --content TEXT --title TEXT]
               [--source SOURCE] [--external-id ID] [--note TEXT] [--fetch | --no-fetch]
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `TASK_ID` | Yes | The task to link to |

**Options:**

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--item-id` | id | | Link an existing item |
| | `--url` | url | | Create and link a new item from this URL |
| | `--content` | text | | Create and link a new item from this content |
| | `--title` | text | `""` | Title for the new item |
| | `--source` | slack \| github \| gdrive \| url \| note \| commit \| file | (inferred) | Source for the new item |
| | `--external-id` | id | | External id for the new item |
| | `--note` | text | `""` | A note recorded with the association |
| | `--fetch` / `--no-fetch` | bool | fetch on | Fetch the new item's content on create |

Provide either `--item-id` or one of `--url`/`--content`/`--title`; the command rejects a call with none of them.

**Examples:**

```bash
agentic link add 8dcb9b08ca12 --item-id 5f2a1c
agentic link add 8dcb9b08ca12 --url https://github.com/o/r/issues/42 --note "tracked upstream"
```

**Errors:** with no `--item-id` and no new-item input, prints `error: provide --item-id, or a --url/--content for a new item` on stderr and exits 1; an unknown task prints `error: Task not found (HTTP 404)` and exits 1.

### `agentic link remove`

**Description:** Removes an item's association with a task and records a timeline event.
Serves FR-5.

**Synopsis:**

```
agentic link remove TASK_ID ITEM_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `TASK_ID` | Yes | The task to unlink from |
| `ITEM_ID` | Yes | The item to unlink |

**Options:** the global options only.

**Examples:**

```bash
agentic link remove 8dcb9b08ca12 5f2a1c
```

**Errors:** an unknown task or item prints `error: ... (HTTP 404)` and exits 1.

### `agentic task create --github-url`

**Description:** Imports a task from a GitHub issue or PR URL: the title and description are prefilled and the issue is linked as an item.
Serves FR-7 and FR-8 (the GitHub-backed path).
This is the CLI's GitHub import surface; the repository issue picker (FR-8) is web-only.

**Synopsis:**

```
agentic task create --github-url URL
```

**Options:**

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--github-url` | url | | The GitHub issue or PR to import |

**Examples:**

```bash
agentic task create --github-url https://github.com/o/r/issues/42
```

**Errors:** an invalid or unreachable issue prints `error: ... (HTTP <status>)` and exits 1.

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
| 1 | Runtime failure (the API returns an error, the request fails, or a `link add` call carries no item input) |
| 2 | Usage error (unknown option or missing argument) |
| 130 | Interrupted (Ctrl-C) |

## Output Behavior

- **stdout:** item rows (`<id>  <source>  <title-or-url>`), the `created`/`refreshed`/`deleted`/`linked`/`unlinked` confirmation, or the JSON payload.
- **stderr:** error messages only.
- **Machine-readable:** `--format json` (or piping) emits the full API objects, including `task_ids` on items.
- **TTY behavior:** text on a TTY, JSON when piped; no color and no wrapping so piped JSON stays valid.

## Help Text

```
$ agentic item --help
Usage: agentic item COMMAND [OPTIONS]

Create and manage source items (Slack/GitHub/Drive/URL/note).

Commands
  create   Create an item (source is inferred from the url/content; fetches unless --no-fetch).
  delete   Delete an item and its associations.
  get      Show an item.
  list     List items.
  refresh  Re-fetch an item's metadata/content.
```

## Error Messages

- Format: `error: <message> (HTTP <status>)` on stderr for API errors, which exit 1, or a bare `error: <message>` for a client-side check such as `link add` with no item input.
- Usage errors print the parser's Rich error panel (for example `Unknown option: --bogus.`) and exit 2.
- Examples: `error: Item not found (HTTP 404)`, `error: provide --item-id, or a --url/--content for a new item`.

## Interactive Behavior

- **Prompts:** none; every command is non-interactive.
- **Destructive actions:** `item delete` and `link remove` do not prompt (scriptable by design).
- **Dry run:** not offered.

## Example Sessions

### Capture a note and a GitHub issue

```console
$ agentic item create --content "remember to rotate the token"
created 5f2a1c  5f2a1c  note    remember to rotate the token
$ agentic item create --url https://github.com/o/r/issues/42
created 9b71e0  9b71e0  github  Add retry to the fetch
```

### Link an item to a task

```console
$ agentic link add 8dcb9b08ca12 --item-id 9b71e0 --note "tracked upstream"
linked 9b71e0 to 8dcb9b08ca12
$ agentic item get 9b71e0 --format json
{
  "id": "9b71e0",
  "source": "github",
  "kind": "issue",
  "title": "Add retry to the fetch",
  "url": "https://github.com/o/r/issues/42",
  "external_id": "o/r#42",
  "task_ids": ["8dcb9b08ca12"]
}
```

### Import a task from a GitHub issue

```console
$ agentic task create --github-url https://github.com/o/r/issues/42
created 1c02d4  Add retry to the fetch
```

### Error path

```console
$ agentic link add 8dcb9b08ca12
error: provide --item-id, or a --url/--content for a new item
$ echo $?
1
```

## Requirements Traceability

| Requirement | Command(s) / Option(s) | Notes |
|---|---|---|
| FR-1 | `item create`, `item create --source` | Source, kind, and external id inferred when not supplied |
| FR-2 | `item create --content` | Non-URL text is stored as note content; `--url` non-URL is moved to content |
| FR-3 | `item create` | The API deduplicates by source + external id, or by URL |
| FR-4 | `item create` (fetch on), `item refresh`, `--no-fetch` | Title and content fetched on demand |
| FR-5 | `link add`, `link remove`, `--note` | Association changes are recorded on the timeline |
| FR-6 | `item list`, `item get`, `item refresh`, `item delete` | The system's list, read, refresh, and delete are covered; the API and web UI cover `update`, and the CLI has no `item update` (see Open Questions) |
| FR-7 | `task create --github-url` | Prefills the task and links the issue as an item |
| FR-8 | (none) | The repository issue picker is web-only; the CLI imports by URL |
| FR-9 | `item get` (`task_ids`) | `task_ids` are returned in JSON; the items text query has no command (see Open Questions) |

## Out of Scope

- Listing a repository's open issues from the CLI (FR-8); that is the web picker's surface.
- Auto-refreshing items on a schedule (requirements Open Question 1); refresh is on demand.
- A `link list` command: a task's items are shown by `task get`.

## Open Questions

1. Should the CLI gain `item update` to cover FR-6's update case, or is update web-only?
2. Should `item list` gain a `--q` text filter to expose FR-9's search (the API already accepts `q`)?
3. Should `link add` accept `--worktree` or other association kinds, or stay item-only?
