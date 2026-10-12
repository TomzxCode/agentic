---
title: "Repositories, groups, and directory picker"
status: draft
session_link: "http://localhost:10000/?session=ses_ed209e713ffe1UX3Qqhq0UZ7Tw"
---

# CLI Design: Repositories, groups, and directory picker

## Design Principles

- Extends the existing `agentic` CLI conventions: cyclopts commands, `noun subcommand` grouping, long options only, and `--format {auto,json,text}` output (auto is json when stdout is not a TTY).
- The CLI covers the single-repository path (register by path, list, remove).
- Bulk registration, repository groups, and the directory picker stay web-only because they need a multi-select UI or the server filesystem browser (FR-2, FR-4, FR-5, FR-6); the CLI registers one resolved path at a time.
- The CLI never touches files on disk when removing a repository; it deletes the record and its memberships, matching FR-3.
- Destructive commands do not prompt: the CLI is scriptable by design (see Interactive Behavior).

## Command Tree

```
agentic
└── repository              Register local git repositories
    ├── list                List repositories
    ├── add                 Register a local git repository by path
    └── remove              Remove a repository (files are not touched)
```

## Commands

### `agentic repository list`

**Description:** Lists repositories newest-first, one row per repository with its id, name, and absolute path.
Serves FR-3.

**Synopsis:**

```
agentic repository list
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| (none) | | The command takes no arguments |

**Options:** the global options only.

**Examples:**

```bash
agentic repository list
agentic repository list --format json
```

**Errors:** the API returning an error prints `error: ... (HTTP <status>)` and exits 1; an unreachable API currently propagates the connection error (see FEAT-p6 Error Messages).

### `agentic repository add`

**Description:** Registers a local git repository by path, resolving it to an absolute path and detecting its remote URL and default branch.
Serves FR-1.

**Synopsis:**

```
agentic repository add PATH [--name NAME]
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `PATH` | Yes | Path to the git checkout (a path without `.git` is rejected) |

**Options:**

| Short | Long | Value | Default | Description |
|---|---|---|---|---|
| | `--name` | text | the directory name | A display name for the repository |

**Examples:**

```bash
agentic repository add ~/src/app
agentic repository add ~/src/app --name "app"
```

**Errors:** a path that is not a git repository prints `error: <path> is not a git repository (HTTP 400)` and exits 1.

### `agentic repository remove`

**Description:** Removes a repository record and its group memberships, task associations, and worktree rows, removing the worktrees from disk first.
The repository's files on disk are never touched.
Serves FR-3.

**Synopsis:**

```
agentic repository remove REPOSITORY_ID
```

**Positional arguments:**

| Argument | Required | Description |
|---|---|---|
| `REPOSITORY_ID` | Yes | The repository to remove |

**Options:** the global options only.

**Examples:**

```bash
agentic repository remove 3ad9f1
```

**Errors:** an unknown repository prints `error: Repository not found (HTTP 404)` and exits 1.

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
| `AGENTIC_FS_ROOT` | server (FR-6) | `~` | Root the server-side picker is confined to; not read by the CLI |

The `AGENTIC_*` connection variables are the documented defaults (FEAT-p6 FR-3), but the current launcher does not yet honor them (see FEAT-p6 Open Question 2).

## Configuration

- No config file; flags and environment variables only.
- Precedence: CLI flags > environment variables > defaults.

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Runtime failure (the API returns an error, the request fails, or the path is not a git repository) |
| 2 | Usage error (unknown option or missing argument) |
| 130 | Interrupted (Ctrl-C) |

## Output Behavior

- **stdout:** repository rows (`<id>  <name>  <path>`), the `added`/`removed` confirmation, or the JSON payload.
- **stderr:** error messages only.
- **Machine-readable:** `--format json` (or piping) emits the full API objects.
- **TTY behavior:** text on a TTY, JSON when piped; no color and no wrapping.

## Help Text

```
$ agentic repository --help
Usage: agentic repository COMMAND [OPTIONS]

Register local git repositories.

Commands
  add     Register a local git repository by path.
  list    List repositories.
  remove  Remove a repository (files are not touched).
```

## Error Messages

- Format: `error: <message> (HTTP <status>)` on stderr for API errors, which exit 1.
- Usage errors print the parser's Rich error panel (for example `Unknown option: --bogus.`) and exit 2.
- Example: `error: /tmp/not-a-repo is not a git repository (HTTP 400)`.

## Interactive Behavior

- **Prompts:** none; every command is non-interactive.
- **Destructive actions:** `repository remove` deletes the record and its memberships and does not prompt (scriptable by design); it never deletes files on disk.
- **Dry run:** not offered.

## Example Sessions

### Register and list repositories

```console
$ agentic repository add ~/src/app
added 3ad9f1  app  /home/user/src/app
$ agentic repository list
3ad9f1  app  /home/user/src/app
```

### Remove a repository

```console
$ agentic repository remove 3ad9f1
removed 3ad9f1
```

### Error path

```console
$ agentic repository add /tmp/not-a-repo
error: /tmp/not-a-repo is not a git repository (HTTP 400)
$ echo $?
1
```

## Requirements Traceability

| Requirement | Command(s) / Option(s) | Notes |
|---|---|---|
| FR-1 | `repository add`, `--name` | The server resolves the path and detects remote URL and default branch |
| FR-2 | (none) | Bulk add is the web picker's path (`POST /api/repositories/bulk`), which reports per-path errors |
| FR-3 | `repository list`, `repository remove` | Remove clears memberships and worktrees but never touches files on disk |
| FR-4 | (none) | Group creation and member editing are web-only |
| FR-5 | (none) | Group list, read, update, and delete are web-only |
| FR-6 | (none) | The directory picker is a server-side browser served to the web UI |

## Out of Scope

- Groups (`repository group ...`): no CLI surface today (FEAT-p3 FR-4, FR-5 are web-only).
- Bulk add (`--paths`): the multi-select flow lives in the web picker.
- A `repository get` command: `repository list --format json` returns the same fields.
- The directory picker endpoints (`GET /api/fs/list`): a browser file input cannot reveal server paths, so the picker is a server-side web concern.

## Open Questions

1. Should the CLI expose repository groups (`repository group list|create|update|delete`) so agents can manage groups without the web UI?
2. Should `repository add` gain repeatable `--path` arguments for a scriptable bulk add (FR-2)?
