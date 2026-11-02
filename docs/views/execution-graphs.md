# Execution graphs

`/graphs` holds workflows: named DAGs of steps that run by hand, from a schedule trigger node in the graph, or from a webhook event delivered to the `Webhooks` page.

## Problem

Some work is more than one step: run an agent, hand its answer to a command, build something, then ask a person to approve.
Keeping that in a shell script hides the steps, and keeping it in your head loses the record.
An execution graph stores the steps once and runs them with their statuses and outputs visible.

## The page

| Tab | What it shows |
| --- | --- |
| `Graphs` | One row per graph, with its schedules, next run, step count, a `Run` button, the editor, settings, and delete. |
| `Executions` | Every execution across graphs, newest first, expandable into each node's status and output, with a pending form and a cancel button. |

## Triggers

A trigger is a node in the graph, added from the **+ Add step** menu like any other step.
A **schedule trigger** holds a five-field cron expression and the zone it is read in; the inspector previews the next five runs, and its enabled checkbox pauses it.
An **event trigger** is the entry point for a webhook payload: each of its fields reads one JSON path and feeds a downstream input.
A graph may hold several schedule triggers and at most one event trigger; neither takes an incoming connection.
`Run` is always available, whatever triggers the graph has.

The `Webhooks` page owns the inbound side of events: an endpoint with subscriptions that match event types and JSON paths, start a graph, and hand the payload to its event trigger node.

## Steps

A graph is a set of nodes wired by edges.
An edge feeds one upstream output into one downstream named input.

| Step | What it does | Output |
| --- | --- | --- |
| **Agent run** | Sends a prompt to an ACP harness in a working directory, optionally with a model override. | The agent's final answer. |
| **Agentic command** | Runs an `agentic` CLI command line against this server (`agentic --format json …`). | The command's stdout (JSON in practice). |
| **Shell script** | Runs a bash script with `bash -c`, timed out by `AGENTIC_SCHEDULED_TASK_TIMEOUT`. | The script's combined stdout and stderr. |
| **Form** | Pauses the execution until someone answers fields in the web UI. | Each field's answer. |
| **Event trigger** | The entry point for a webhook event. | One value per configured JSON path. |
| **Schedule trigger** | Starts the graph on a cron expression; it produces nothing and feeds no step. | None. |

Every non-form output step may declare named inputs and reference them in its text as `{{name}}`, `{{name[0]}}`, or `{{name.join(", ")}}`.
A node whose upstream failed is skipped, and a failure settles the execution as failed.

### Agent runs

An agent-run node picks a harness (or the default one), an optional model, an optional working directory, and a prompt.
Without a working directory it runs in the execution task's worktree or first repository.
The run is a normal queued agent run linked to both the execution and the node, so its transcript is on the execution's task.

### Agentic commands

An Agentic command node runs the app's own CLI against the running server, for example:

```text
task create --title "Fix {{title}}" --body "{{body}}"
```

Its stdout is the node's output, so a following step can consume the created task's JSON.

### Shell scripts

A Shell script node runs a bash script:

```bash
set -euo pipefail
make build
echo "built {{name}}"
```

Pipes, redirects, and `&&` work as written.
A non-zero exit, a timeout, or an empty rendered script fails the node.
The script has `AGENTIC_API_URL` set to the server, so it can call `agentic` too when that is simpler than an Agentic command node.

### Forms and event triggers

A Form asks for fields only when a downstream step is otherwise ready, then flows its answers downstream like an output.
An Event trigger is optional and limited to one per graph; its fields are JSON paths into the webhook payload (`pull_request.title`, `action`, …) and it cannot take an incoming edge.
A manual or scheduled run of a graph with an event trigger gives every event field an empty value.

## Editing

`Edit graph` opens the canvas:

- Add a step from the **+ Add step** menu, which lists each node type with what it does.
- Tap an output row, then tap the input or form field it should feed; on a computer you can also drag from a right-side dot. While a connection is armed, the eligible rows are highlighted.
- Drag a card by its header to move it; a swipe over the card body pans the canvas on a phone.
- Select a card to edit it in the inspector. Tap a connection line to select it, then press `Remove`.
- `Arrange` lays every step out by dependency layer; `Auto-layout` does it as steps and connections are added or removed.
- `Check` reports problems; `Save` stores the draft; `Run` saves and starts an execution.

A definition is stored in one JSON column and normalized on read, so a graph saved by an older version still loads.
The internal kind names (`run`, `cli`, `shell`, `form`, `trigger`) stay stable, and a trigger node carries its `triggerType` (`event` or `schedule`); the editor shows the display names.

## CLI and HTTP

| Operation | CLI | HTTP |
| --- | --- | --- |
| List | `agentic graphs list` | `GET /api/graphs` |
| Read one | `agentic graphs get <graph>` | `GET /api/graphs/{id}` |
| Create | `agentic graphs create --name "Build" --definition graph.json` | `POST /api/graphs` |
| Update | `agentic graphs update <graph> --definition graph.json` | `PATCH /api/graphs/{id}` |
| Delete | `agentic graphs delete <graph>` | `DELETE /api/graphs/{id}` |
| Run now | `agentic graphs run <graph>` | `POST /api/graphs/{id}/run` |
| Executions | `agentic graphs executions` | `GET /api/graphs/executions` |
| One execution | `agentic graphs executions <execution>` | `GET /api/graphs/executions/{id}` |
| Answer a form | none | `POST /api/graphs/executions/{id}/forms/{node_id}` |
| Cancel | none | `POST /api/graphs/executions/{id}/cancel` |

## Related

- [How to trigger a workflow from a webhook](../how-to/trigger-workflows-from-webhooks.md).
- [Webhooks view](webhooks.md) for the event entry points.
- [CLI reference](../reference/cli.md) and [HTTP API](../reference/http-api.md).
