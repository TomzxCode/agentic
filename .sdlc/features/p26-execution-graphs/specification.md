---
title: "Execution graphs"
status: done
revision: 1
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Specification: Execution graphs

## Overview

`graphs.py` owns the orchestration: a definition contract (`normalize_definition`, `validate_definition`, `render_template`, `topological_order`), an async executor that walks the DAG in the API process, the form answer handoff, schedule-trigger node firing, and startup reconciliation.
`models/graphs.py` defines two tables: `ExecutionGraph` holds the saved definition (nodes and edges as JSON, there are no graph node or edge tables) plus the derived `schedule_state` bookkeeping, and `GraphExecution` holds one run of it, including the executor's working state as a JSON column.
A schedule is a trigger node in the definition (`kind: trigger`, `triggerType: schedule`), so the cron lives with the rest of the graph; a webhook event is a trigger node fed by the separate Webhooks subscriptions.
`routers/graphs.py` exposes CRUD, a validate-without-saving endpoint, run-now, the execution history and detail, cancel, and the form-answer endpoint that unblocks a paused execution.
Every run node becomes an `AgentRun` (kind `graph`) linked to the execution and node through `graph_execution_id` and `graph_node_id`, attached to a task the execution creates.
The SPA adds the `/graphs` page (`GraphsList`, `GraphEditor`, `GraphExecutions`, `GraphMetaForm`, `ExecutionGraphsView`, plus the pure `executionGraph.js` editor logic), and the CLI adds an `agentic graphs` command group.

## Architecture

```mermaid
flowchart LR
    G[ExecutionGraph] --> D[definition: nodes with schedule/event trigger nodes]
    G --> SS[schedule_state: next and last occurrence per schedule node]
    G --> E[GraphExecution]
    E --> S[state JSON: nodes, outputs, formValues, pendingForm, trigger]
    EX[graphs.py executor] --> AR[AgentRun kind=graph]
    EX --> CLI[agentic CLI child process]
    AR --> Q[SAQ queue]
    S --> R[routers/graphs.py]
    D --> R
    SS --> R
    R --> SPA[GraphsList / GraphEditor / GraphExecutions]
    R --> C[agentic graphs]
    SCH[scheduler_loop] --> SS
    SCH --> EX
    WH[Webhooks event bus] --> EX
    REC[reconcile_graph_executions] --> E
```

## Data Models

### ExecutionGraph

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | string | PK | Graph id |
| name | string | not null | Label shown in lists and the task title |
| description | string | default "" | What the graph does |
| definition | JSON | default {} | `{"nodes": [...], "edges": [...]}` as the editor arranged it, including any trigger nodes |
| schedule_state | JSON \| None | None | Derived: `{nodeId: {nextRunAt, lastRunAt, cron, timezone}}` for enabled schedule nodes |
| last_run_at | datetime \| None | None | When the graph last started an execution |
| created_at / updated_at | datetime | not null | Bookkeeping |

The pre-trigger `schedule`, `timezone`, `enabled`, and `next_run_at` columns remain on old databases but are no longer read; the migrations moved a schedule into the definition.
`schedule_state` is never user-edited: `sync_schedule_state` seeds it on save, keeps an unchanged node's pending occurrence, and drops entries for disabled or removed nodes.
A graph may hold several schedule trigger nodes and at most one event trigger node.

### GraphExecution

| Field | Type | Constraints | Description |
|---|---|---|---|
| id | string | PK | Execution id |
| graph_id | string | FK executiongraph, index, not null | Owning graph |
| task_id | string | FK task, index, not null | Task that groups the execution's runs |
| trigger | string | default manual | manual, schedule, or event:<type> |
| trigger_id | string | default "" | The trigger row that started it, empty for a manual run |
| status | GraphExecutionStatus | default running | running, succeeded, failed, cancelled |
| error | string | default "" | Settling error, empty on success |
| state | JSON | default {} | Executor state: `order`, per-node `nodes` (status, runId, error, startedAt, endedAt), `outputs`, `formValues`, `pendingForm` |
| started_at | datetime | not null | When the execution started |
| ended_at | datetime \| None | None | Stamped when it settles |

`state` is written on every node transition.
Writers assign a fresh dict to the column (in-place edits are invisible to SQLAlchemy) and the executor merges concurrent writes with `_merged_state`, so a form answer the endpoint stored is folded into the working copy.

### AgentRun link columns

| Field | Type | Description |
|---|---|---|
| graph_execution_id | string \| None, index | The execution this run belongs to |
| graph_node_id | string \| None | The definition node this run implements |

### Definition contract

A node is one of three kinds:

| Kind | Fields | Output |
|---|---|---|
| run | harnessId, model, cwd, promptTemplate, inputs `[{id, name}]` | The run's final answer (messages, falling back to thoughts) |
| cli | command, cwd, inputs | The command's stdout, run in JSON mode |
| form | fields: id, title, type (text, textarea, number, date, time, select, slider, checkbox), required, placeholder, defaultValue, select options (max 20), numeric min/max/step | One value per field |

An edge is `{id, source, sourceFieldId, target, targetInputId, targetFieldId}`: a run or cli source feeds its single output, a form source feeds one field, and the target is a named input (run, cli) or a field default (form).
Caps: 32 nodes, 20 fields per form, 20 select options, 20,000 characters of output.
The template language is `{{name}}` (join values with newlines), `{{name[2]}}` (one value), and `{{name.join(", ")}}` (join with a separator); an unknown name or out-of-range index fails the node and leaves the placeholder in place.
Node statuses are pending, waiting (a form waiting for an answer), running, done, failed, and skipped.

### Editor layout

`executionGraph.js` positions a node's card on the canvas from `position` in the definition, so a save keeps the arrangement.
`relayout` places every node in the column of its dependency layer and in the row of the node it follows when that row is free, so a chain reads on one line; a definition with a cycle is left as it is and the cycle is reported as a validation issue instead.
`autoLayout` applies the same placement only to nodes that have never been positioned, so opening a graph never moves cards the user dragged.
The editor's Arrange button runs `relayout` over the whole definition.
Its Auto-layout select (never, on add, on remove, always) decides whether adding or removing a node or a connection re-runs it: a new link can move a node into a deeper layer, and dropping one can pull it back; the choice is a per-device preference in `localStorage`, not graph state.

Linking works by two taps on a phone: tapping a source row arms it, every eligible target row is marked, and a second tap draws the edge, so the finger is never held while the canvas scrolls to an off-screen node.
A press that releases on the same row without moving arms it; a press that moves draws the connection; a release within 48 px of an eligible port (`nearestPort`) snaps to that port, which covers a finger that missed the row by a few pixels.
The card header is the drag handle and the only part that keeps `touch-action: none`; a swipe over a card body pans the canvas, so cards no longer block scrolling on a phone.
Rows are 32 px tall so a tap lands inside the row it aims at, and an input's dot sits beside its label instead of at the opposite edge.

A connection is selected by tapping anywhere within 24 px of its curve, through a transparent hit path drawn over the visible stroke; the banner then names both ends and its Remove button disconnects them, so no Delete key is needed on a phone.

## API Contracts

| Method | Path | Purpose |
|---|---|---|
| GET | /api/graphs | List graphs (soonest next schedule run first, manual-only last) |
| POST | /api/graphs | Create a graph with its definition (including trigger nodes) |
| POST | /api/graphs/validate | Check a definition without saving |
| GET | /api/graphs/executions | Every execution across graphs, newest first (limit 1-500, default 100) |
| GET | /api/graphs/executions/{execution_id} | One execution's nodes, outputs, and pending form |
| POST | /api/graphs/executions/{execution_id}/cancel | Cancel a running execution |
| POST | /api/graphs/executions/{execution_id}/forms/{node_id} | Answer or cancel the form the execution waits on |
| GET | /api/graphs/{graph_id} | Read one graph with its definition |
| PATCH | /api/graphs/{graph_id} | Update name, description, and definition |
| DELETE | /api/graphs/{graph_id} | Delete the graph, its definition, and its execution history |
| POST | /api/graphs/{graph_id}/run | Start an execution now (trigger `manual`), in the background |

`ExecutionGraphCreate`, `ExecutionGraphUpdate`, and `ExecutionGraphRead` carry the definition, whose trigger nodes hold the schedule; there is no graph-level trigger payload.
`ExecutionGraphRead` derives `next_run_at` as the earliest enabled schedule node's occurrence from `schedule_state` and adds `running_execution_id`, so the list can badge what is in flight.

Status codes: 201 on create and run; 200 on read, update, validate, cancel, and form answers; 204 on delete; 400 for a blank name or a definition that fails validation at run time; 404 for a missing graph or execution; 409 when the graph already has a running execution, the execution is not running, or it is not waiting on that form. Webhook ingress lives under `/api/webhooks` and `/api/hooks`.

The execution detail reads the live run row as the truth about a run node: succeeded maps to done, failed to failed, cancelled to skipped, and queued or running pass through.

## Key Flows

### Run now and walk the DAG

```mermaid
sequenceDiagram
    autonumber
    participant C as Client / CLI
    participant R as graphs router
    participant X as graphs.py executor
    participant Q as SAQ queue
    participant DB as SQLite
    C->>R: POST /api/graphs/{id}/run
    R->>X: start_execution
    X->>DB: INSERT task "[Graph] name", INSERT GraphExecution, timeline graph_started
    X-->>R: execution id (201)
    loop until every node settles
        X->>X: start ready nodes (render prompt, enqueue run / run cli / request form)
        X->>DB: persist state
        X->>Q: enqueue_run(run_id)
        X->>DB: poll run rows at 1 Hz
    end
    X->>DB: finalize status, ended_at, timeline graph_finished
```

### A trigger starts the graph

```mermaid
sequenceDiagram
    autonumber
    participant SCH as scheduler_loop
    participant WH as Webhooks event bus
    participant D as definition schedule node
    participant X as graphs.py executor
    participant DB as SQLite
    SCH->>D: enabled schedule node whose state occurrence passed
    SCH->>DB: advance schedule_state, stamp lastRunAt
    SCH->>X: start_execution(trigger="schedule", trigger_id=node id)
    WH->>X: start_execution(trigger="event:type", event=payload)
    X->>DB: INSERT GraphExecution with the trigger and node id
```

A disabled trigger, a webhook trigger whose secret does not match, a trigger of another type, and a graph that already has a running execution are all refused.
The manual Run action records `trigger = "manual"` with no trigger id.

### Form answer unblocks a paused execution

```mermaid
sequenceDiagram
    autonumber
    participant X as executor
    participant DB as SQLite
    participant R as graphs router
    participant U as User (web UI)
    X->>DB: state.pendingForm = {nodeId, defaults}, node waiting
    U->>R: GET /api/graphs/executions/{id} (pending_form)
    U->>R: POST .../forms/{node_id} {values}
    R->>DB: fresh state dict: formValues, node done, pendingForm cleared
    R-->>X: future resolved
    X->>DB: _merged_state folds the answers in, walk resumes
```

### Failure, cancel, and restart

- A run that fails, a command that exits non-zero, or a render error fails the node; every downstream node is skipped; the execution settles as failed and names the first failed node.
- Cancelling cancels the orchestrator task, whose handler aborts active runs (marked skipped), releases any pending form, and settles the row as cancelled.
- `reconcile_graph_executions` runs at startup and marks every execution still `running` as failed with "Interrupted by a server restart"; the agent runs it had enqueued finish on the queue on their own.

## Technical Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Definition storage | JSON column on the graph, no node or edge tables | A graph is edited and read as one document; separate tables would buy nothing the editor needs |
| Walk location | The API process, runs durable on SAQ | The walk is cheap orchestration; the expensive runs survive a restart as queue jobs, so only the walk needs reconciliation |
| Run settlement | Poll the run row at 1 Hz instead of subscribing to streams | A run lasts seconds to minutes, so polling is imperceptible and avoids stream plumbing |
| Form pause | Pending request in state plus an in-process future | The API answers the form on any process copy of the state; the merge step keeps the executor's copy current |
| CLI nodes | Shell out to the app's own `agentic` CLI in JSON mode | Lets a graph call every CLI capability without new internal APIs |
| Scheduled fires | Advance the occurrence before starting, skip when busy | A slow execution is never fired twice for one occurrence, and a busy graph drops the tick rather than queueing it |
| Restart handling | Mark lost executions failed, never resume | The walk holds in-process futures that cannot be reconstructed; the runs themselves are safe |
| Schedules as nodes | A schedule is a trigger node in the definition, with cron, zone, and enabled on the node; `schedule_state` holds only its derived next and last occurrence | The schedule is edited where the graph is built, and the graph row carries no trigger configuration |
| Schedule state | A JSON map keyed by node id, seeded and pruned on save | The scheduler needs a pending occurrence per node, but the definition stays the source of truth |
| Editor checks | Mirror server validation locally in `executionGraph.js` | Instant feedback while typing, with the server as the authority at save and run time |

## Risks and Unknowns

1. A restart kills a paused execution, so a user answering a form after a restart gets a 409 and the execution shows as failed; reconciliation is the designed behavior, not a bug, but it is worth knowing.
2. Outputs and form defaults are truncated at 20,000 characters, so a very long answer loses its tail as a downstream input.
3. A scheduled fire on a busy graph is skipped entirely, not queued; a graph that runs longer than its interval silently loses ticks.
4. A schedule node's next occurrence is computed from the definition; editing the definition outside the API leaves stale state until the next scheduler tick reconciles it.
5. Webhook ingress is now the separate Webhooks feature; a graph that only has a schedule node will not start from an event until an event trigger node and a subscription exist.

## Out of Scope

- Parallel branches beyond what the DAG already allows (nodes run in dependency order, not with concurrency controls).
- Retries, per-node timeouts beyond the CLI timeout, or resuming a failed execution.
- Versioning of definitions or an execution audit beyond the state column and timeline entries.
- Nested graphs (a graph node that runs another graph).
