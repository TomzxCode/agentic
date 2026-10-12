---
title: "People: associate tasks and items with specific individuals"
status: draft
session_link: "http://localhost:10000/?session=ses_ed1c7d2feffevews1ZEr34mSZC"
---

# CLI Design: People

## Design Principles

- Extends the existing `agentic` CLI conventions: cyclopts commands, `noun subcommand` grouping, long options only, and `--format {auto,json,text}` output (auto is json when stdout is not a TTY).
- The CLI is a thin client over the HTTP API; every command maps to one people endpoint, so semantics match the API and the SPA (NFR-2).
- `task get` shows the task's people alongside its items, so the CLI reader sees the same picture the task page does.

## Command Tree

```
agentic
├── person                  Create and manage people and their links
│   ├── list                List people with their task and item counts
│   ├── get                 Show a person and what they are linked to
│   ├── create              Create a person
│   ├── update              Update a person's fields
│   ├── delete              Delete a person and their links
│   ├── link                Link a person to a task or an item
│   └── unlink              Unlink a person from a task or an item
└── task
    └── get                 Show a task, now including its people
```

## Commands

### `agentic person list`

**Description:** Lists people, each with the number of tasks and items they are linked to, ordered by name (case-insensitive).
Serves FR-4 and FR-5.

**Synopsis:**

```
agentic person list
```

**Options:**

| Long | Value | Default | Description |
|---|---|---|---|
| `--format` | auto \| json \| text | auto | Output format |
| `--api-url` | url | `$AGENTIC_API_URL` or `http://127.0.0.1:8600` | API base URL |
| `--timeout` | seconds | 60 | Per-request timeout |

**Examples:**

```bash
agentic person list
agentic person list --format json
```

**Errors:** an API error prints `error: ... (HTTP <status>)` to stderr and exits 1.

### `agentic person get`

**Description:** Shows a person with the tasks and items they are linked to.
Serves FR-5.

**Synopsis:**

```
agentic person get PERSON_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `PERSON_ID` | Yes | The person to show |

**Examples:**

```bash
agentic person get 1a2b3c4d5e6f
```

**Errors:** an unknown person prints `error: Person not found (HTTP 404)` and exits 1.

### `agentic person create`

**Description:** Creates a person.
Serves FR-1 and FR-5.

**Synopsis:**

```
agentic person create --name TEXT [--email TEXT] [--handle TEXT] [--notes TEXT]
```

**Options:**

| Long | Value | Default | Description |
|---|---|---|---|
| `--name` | text | (required) | The display name |
| `--email` | text | | Contact email |
| `--handle` | text | | Chat or login handle |
| `--notes` | text | | Free-form notes |

**Examples:**

```bash
agentic person create --name "Ada Lovelace" --handle ada
```

**Errors:** a blank name prints `error: Name is required (HTTP 400)` and exits 1.

### `agentic person update`

**Description:** Updates a person's fields.
Serves FR-5.

**Synopsis:**

```
agentic person update PERSON_ID [--name TEXT] [--email TEXT] [--handle TEXT] [--notes TEXT]
```

### `agentic person delete`

**Description:** Deletes a person and their links.
Serves FR-10.

**Synopsis:**

```
agentic person delete PERSON_ID
```

### `agentic person link` / `agentic person unlink`

**Description:** Links or unlinks a person to a task (`--task`) or an item (`--item`).
Serves FR-2, FR-3, and FR-5.

**Synopsis:**

```
agentic person link PERSON_ID --task TASK_ID
agentic person link PERSON_ID --item ITEM_ID
agentic person unlink PERSON_ID --task TASK_ID
agentic person unlink PERSON_ID --item ITEM_ID
```

**Options:**

| Long | Value | Default | Description |
|---|---|---|---|
| `--task` | task id | | The task to link or unlink |
| `--item` | item id | | The item to link or unlink |

**Examples:**

```bash
agentic person link 1a2b3c4d5e6f --task 8dcb9b08ca12
agentic person unlink 1a2b3c4d5e6f --item 7f6e5d4c3b2a
```

**Errors:** providing neither `--task` nor `--item` prints `error: provide --task or --item` and exits 1; an unknown id prints the API's 404 message and exits 1.

## Global Options

| Long | Value | Default | Description |
|---|---|---|---|
| `--api-url` | url | `$AGENTIC_API_URL` or `http://127.0.0.1:8600` | API base URL |
| `--format` | auto \| json \| text | auto | Output format (`auto` is json when stdout is not a TTY) |
| `--timeout` | seconds | 60 | Per-request timeout |
| `--help` | | | Show help and exit |

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

- **stdout:** person rows (`<id>  <name>  tasks:<n> items:<n>`) or the JSON payload.
- **stderr:** error messages only.
- **Machine-readable:** `--format json` (or piping) emits the full API objects.
- **TTY behavior:** text output on a TTY, JSON when piped; output is not colorized or wrapped so piped JSON stays valid.

## Help Text

```
$ agentic person --help
Usage: agentic person COMMAND [OPTIONS]

Create and manage people and their links.

Commands
  list    List people with their task and item counts.
  get     Show a person and what they are linked to.
  create  Create a person.
  update  Update a person's fields.
  delete  Delete a person and their links.
  link    Link a person to a task or an item.
  unlink  Unlink a person from a task or an item.
```

## Error Messages

- Format: `error: <message> (HTTP <status>)` on stderr.
- Example: `error: Person not found (HTTP 404)`.

## Interactive Behavior

- **Prompts:** none; every command is non-interactive.
- **Destructive actions:** `person delete` removes the person and their links; it does not prompt (scriptable by design).
- **Dry run:** not applicable.

## Example Sessions

### List people

```console
$ agentic person list
1a2b3c4d5e6f  Ada Lovelace  tasks:2 items:1
9f8e7d6c5b4a  Grace Hopper  tasks:0 items:0
```

### Link a person to a task

```console
$ agentic person link 1a2b3c4d5e6f --task 8dcb9b08ca12
linked 1a2b3c4d5e6f to task 8dcb9b08ca12
$ agentic task get 8dcb9b08ca12
8dcb9b08ca12  [open] p2  Fix flaky ingest test
  people: Ada Lovelace
```

### Error path

```console
$ agentic person get does-not-exist
error: Person not found (HTTP 404)
$ echo $?
1
```

## Requirements Traceability

| Requirement | Command(s) / Option(s) | Notes |
|---|---|---|
| FR-1 | `person create` | Name required; email, handle, and notes optional |
| FR-2 | `person link --task`, `person unlink --task` | Task-side link |
| FR-3 | `person link --item`, `person unlink --item` | Item-side link |
| FR-4 | `person list` | Returns `{task_count, item_count}` |
| FR-5 | all `person` commands, `task get` | The CLI surface for the directory and the links |
| FR-10 | `person delete` | Removes the person and their links |

## Out of Scope

- Merging duplicate people.
- Auto-linking people from item metadata.
- A `--any`/`--all` style filter over people.
