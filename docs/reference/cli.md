# CLI

Agentic installs three command-line tools.

| Command | Role |
| --- | --- |
| `agentic` | The user client. Talks to a running API over HTTP, so agents and people can drive the app's content without touching the database. |
| `agentic-server` | The backend. Runs the server and reports its configuration. |
| `agentic-stack` | The optional tray and global-hotkey companion for the focus stack. See [Use the focus stack](../how-to/use-the-focus-stack.md). |

## Install

`uv sync` in the repository root puts the commands in the repository's `.venv`.

To use `agentic` from anywhere, install it as a [uv tool](https://docs.astral.sh/uv/concepts/tools/):

```bash
uv tool install ./cli          # from the repository root
uv tool install -e ./cli       # editable: code changes apply immediately
```

`-e` links the command to the working tree, so edits under `cli/src/` take effect without reinstalling.
This installs `agentic` only; run the backend from the workspace with `uv run agentic-server`.

## Global options

| Option | Purpose |
| --- | --- |
| `--api-url` | API base URL. The default is `http://127.0.0.1:8600`. |
| `--format` | `json` or `text`. Defaults to JSON when the output is piped, text otherwise. |
| `--timeout` | Request timeout. |

Point the client elsewhere with `--api-url`:

```bash
agentic --api-url http://box:8600 task list | jq '.[].id'
```

The client does not read `AGENTIC_API_URL`; pass `--api-url` explicitly.

## Commands by resource

Run `agentic --help` for the full tree, grouped by resource.

### Tasks

```bash
agentic task create --title "Fix the flaky ingest test" --tags bug --tags ci
agentic task create --title "Ship the beta" --deadline 2026-11-01T17:00
agentic task create --slack-url https://acme.slack.com/archives/C123/p1700000000000000
agentic task list --status open
agentic task list --tag bug          # every given tag must match
agentic task update <task> --clear-deadline
agentic task deadlines               # due in the next 7 days, overdue first
agentic task deadlines --within-days 30
agentic task link <task> <other> --relation before   # other must be done first
agentic task link <task> <other>                     # other follows (after)
agentic task deps <task>             # tasks linked before and after
agentic task unlink <task> <other>
agentic graph                        # the whole before/after DAG (nodes and edges)
agentic tag list                     # tags in use, with task counts
```

### Stack

```bash
agentic stack push --title "Fix the flaky ingest test"   # add to the top, becomes current
agentic stack push --title "Then write the notes" --position next
agentic stack list                   # current task first
agentic stack current                # just the current task
agentic stack pop                    # complete the current task, promote the next
agentic stack promote <entry>        # make an entry current
agentic stack reorder <entry> 3      # move an entry to position 3
agentic stack history                # popped and removed entries
```

### Items and links

```bash
agentic link add <task> --url https://github.com/o/r/issues/482
agentic link add <task> --item-id <item>
agentic item refresh-due             # run one refresh pass immediately
```

### Worktrees, runs, and context

```bash
agentic worktree create <task>
agentic context refresh <task>       # agent rewrites summary and next steps
agentic run create <task> --prompt "Investigate the failure"
agentic run wait <run-id>            # block until it finishes
agentic run stream <run-id>          # live transcript
```

### Sessions

```bash
agentic session add <task> <session-id> --cwd /path/to/checkout --label "repro"
agentic session list <task>          # recorded sessions, with reopen links
agentic session get <task> <session> # one session and how to reopen it
agentic session remove <task> <session>
```

`--harness-id` overrides the harness a session is recorded against; it defaults to the task's harness.

### Changes and metrics

```bash
agentic change create <task> --title "Fix the flaky ingest test" --change-class bugfix
agentic change accept <change>       # also: verify, reject, revert, intervene
agentic metrics show                 # autonomy rate and yield, with direction
agentic metrics baseline set autonomy_rate 0.2
```

### People and operations

```bash
agentic person create --name "Ada Lovelace" --handle ada
agentic person link <person> --task <task>          # also: --item <item>
agentic person link <person> --requested-by <task>  # they asked for the task
agentic person list                  # people with task and item counts
agentic operation list --actor agent # audit log: what changed, from where, by whom
```

### Settings

```bash
agentic settings set --slack-refresh-policy "1d=1h,*=7d" --github-refresh-policy "1d=1h,30d=1d"
```

### Backend

```bash
agentic-server                  # start the server (same as: agentic-server serve)
agentic-server serve --reload
agentic-server worker           # process queued agent runs; run alongside the API
agentic-server info             # data dir, database, queue, harness availability
```

## Resources

`agentic` exposes these top-level resources: `task`, `tag`, `stack`, `item`, `link`, `person`, `repository`, `worktree`, `run`, `session`, `context`, `harness`, `settings`, `change`, `metrics`, `operation`, `graph`, and `health`.
