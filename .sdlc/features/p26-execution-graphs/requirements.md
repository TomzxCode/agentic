---
title: "Execution graphs"
status: done
session_link: "http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl"
---

# Requirements: Execution graphs

## Overview

An execution graph is a saved DAG of steps that the app runs on demand or from one of its triggers, such as a cron schedule or an incoming webhook.
A step is either an agent run (a prompt template with named inputs), a CLI command (an `agentic` command line whose placeholders fill its arguments), or a form (fields a human answers in the web UI).
An edge feeds one upstream output (an agent run's final answer, a command's stdout, or a form field's value) into one downstream input.
Each execution creates a task that groups the agent runs it spawns, records per-node status and output as it walks the graph, and pauses on a form node until someone answers.
The web editor draws the graph on a canvas, and the CLI can list, create, edit, run, and inspect graphs for agents.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Sole user | Compose multi-step agent pipelines once, then fire them by hand or on a schedule |
| Coding agent | Create, edit, run, and inspect graphs through the CLI |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall store an execution graph with a name, description, a definition of nodes and edges (at most 32 nodes), and a list of triggers that start it without a manual run. |
| FR-2 | Must | The system shall support three node kinds: run (harness, model, working directory, prompt template, named inputs), cli (command line, working directory, named inputs), and form (at most 20 fields of type text, textarea, number, date, time, select, slider, or checkbox, each with required flag, placeholder, default value, select options, and numeric ranges). |
| FR-3 | Must | The system shall let an edge wire one upstream output (a run node's answer, a cli node's stdout, or a form field) into one downstream named input or form field default, and shall refuse a self connection and a duplicate connection. |
| FR-4 | Must | The system shall normalize every stored or submitted definition by dropping unknown keys, unknown node kinds, and unknown field types, coercing ids and positions, and keeping only the first entries within the caps. |
| FR-5 | Must | The system shall validate a definition and report every problem in plain English: at least one node, unique node ids and titles, a non-empty prompt or command, every placeholder matched to a declared and connected input, form field rules (titled fields, select options, min below max, positive step), edges that point at existing ports, and no circular connection. |
| FR-6 | Should | The system shall validate a definition (and its schedule and timezone) without saving it, so the editor can check work in progress. |
| FR-7 | Must | The system shall create, list, read, update, and delete graphs, listing enabled ones first then soonest next run first, and shall normalize but never reject a definition at create time so an empty shell can be built in the editor; deleting a graph also deletes its execution history while past runs stay on their tasks. |
| FR-8 | Should | The system shall compute each enabled schedule trigger's next occurrence on create, edit, and fire, keep a pending occurrence when only the graph's name or description changes, clear it when the trigger is disabled, and never fire the same occurrence twice. |
| FR-9 | Should | The system shall tick on a timer and start every graph with an enabled schedule trigger whose next occurrence has passed, advancing that trigger's occurrence before starting so a slow execution is never fired twice, and skipping the fire when the graph already has a running execution. |
| FR-10 | Must | The system shall start an execution on request: it creates a task titled `[Graph] <name>` that groups the runs, refuses a second execution while one is running (409), and refuses to run a definition that fails validation (400 with the reasons). |
| FR-11 | Must | The system shall walk the graph in dependency order: render each ready run node's prompt from its gathered input values, enqueue an agent run (kind `graph`, linked to the execution and node) on the queue, poll the run row until it settles, and capture its final answer (messages, falling back to thoughts) as the node's output, truncated to 20,000 characters. |
| FR-12 | Must | The system shall run a cli node by rendering its command line and invoking the app's own `agentic` CLI in JSON mode against the running server, using stdout as the node's output, and failing the node on a render error, a non-zero exit, or a timeout. |
| FR-13 | Must | The system shall skip a node when an upstream node failed or was skipped. |
| FR-14 | Must | The system shall pause the execution on a form node until it is answered in the web UI, requesting the form only once a downstream run is otherwise ready, prefilling defaults from upstream outputs (then field defaults), storing the answers in the execution state, and feeding them downstream like run outputs. |
| FR-15 | Should | The system shall skip a form whose downstream consumers all failed or that no run needs, and shall fail a form whose answer is cancelled, which skips its downstream nodes. |
| FR-16 | Must | The system shall record an execution's lifecycle as running, succeeded, failed, or cancelled, persisting per-node status, timestamps, outputs, form values, and the pending form in a JSON state column written on every transition. |
| FR-17 | Should | The system shall cancel a running execution on request, stopping the walk, aborting its active agent runs, marking their nodes skipped, and settling the row as cancelled. |
| FR-18 | Must | The system shall expose execution history: every execution across graphs newest first, and one execution's detail with each node's kind, status, error, and output, reading the live run row as the truth about a run node's outcome, and exposing the form an execution waits on. |
| FR-19 | Must | The system shall mark executions left `running` by a previous process as failed ("Interrupted by a server restart") when the API starts. |
| FR-20 | Should | The web UI shall provide an Execution graphs page with a Graphs tab (list rows with run, edit, settings, and delete actions, a settings form that edits the graph's name, description, and trigger list, and a canvas editor that adds and drags nodes, wires ports by drag or by two taps, selects a connection and removes it without a keyboard, edits the selected node in an inspector, shows validation issues, saves, and runs, and can arrange every node by dependency layer on demand or automatically when nodes are added or removed, as a per-device preference) and an Executions tab (rows that expand into node statuses and outputs, a pending form dialog, and cancel for a running execution). |
| FR-21 | Should | The CLI shall provide `agentic graphs` commands to list, get, create, update, delete, run, and inspect graphs and executions, loading a definition from a JSON file. |
| FR-22 | Must | The system shall keep each trigger as its own row with a type, a type-specific config, an enabled flag, its next occurrence, and its last run, supporting schedule (a 5-field cron read in an IANA zone) and webhook (an optional shared secret), and shall refuse an unknown type or an invalid config. |
| FR-23 | Should | The system shall start a graph from a webhook trigger on `POST /api/graphs/{graph_id}/triggers/{trigger_id}/fire`, requiring the trigger's secret in the `X-Trigger-Secret` header when it has one, and refusing a disabled trigger, another trigger type, a missing trigger, or a graph that already has a running execution. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Correctness | Writers of the execution state shall assign a fresh object to the JSON column and merge concurrent writes, so form answers stored by the API endpoint are never overwritten by the executor. |
| NFR-2 | Should | Robustness | Normalization, validation, template rendering, and ordering shall be pure functions, testable without a database or event loop. |
| NFR-3 | Should | Performance | The executor shall poll settled run rows at 1 Hz and persist state only on transitions, keeping the cost on SQLite negligible. |
| NFR-4 | Should | Safety | A cli node shall run the virtualenv's own `agentic` binary under the scheduled-task timeout, and cancelling the execution shall kill the child process. |
| NFR-5 | Should | Usability | The editor shall compute the same problems the server reports while the user types, so feedback needs no round trip, while the server stays the authority. |
| NFR-6 | Should | Usability | The graphs page shall stay usable at phone widths, with rows that stack below 760px. |

## Constraints

- Nodes and edges live in the `ExecutionGraph.definition` JSON column; there are no graph node or edge tables.
- Triggers are their own rows (`GraphTrigger`), each with a type and a type-specific config; a graph may have several, and a schedule is one type beside a webhook.
- The orchestration walk lives in the API process; the agent runs it enqueues are durable SAQ jobs that survive a restart on their own.
- A graph has at most one running execution at a time.
- Template placeholders are `{{name}}`, `{{name[2]}}`, and `{{name.join(", ")}}`; input names may not contain whitespace or placeholder grammar characters.
- Node output and form default values are capped at 20,000 characters.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Create a graph with a schedule trigger
      When a graph is created with name "pipeline", a schedule trigger for "*/5 * * * *", and a two-node definition
      Then the response is 201, the trigger is stored with its cron and zone, and next_run_at is set
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Node kinds carry their own fields
      Given a definition with a run node, a cli node, and a form node with a select field
      When the definition is normalized
      Then each node keeps only the fields of its kind
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: Wire an answer into an input
      Given a run node A and a run node B with input "draft"
      When an edge connects A's output to B's "draft" input
      Then the edge is stored
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Garbage is dropped on normalize
      Given a definition with an unknown node kind, a non-object node, and an unknown field type
      When it is normalized
      Then only the known nodes and fields remain and unknown keys are gone
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Validation names the problems
      Given a definition with a missing prompt, an unknown placeholder, a duplicate node id, a select without options, and a cycle
      When it is validated
      Then the issues list names each problem in English
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Validate without saving
      When POST /api/graphs/validate carries a broken definition
      Then the response is 200 with the issues and nothing was stored
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: An empty shell can be stored
      When a graph is created with an empty definition
      Then the response is 201
      And running it is refused with "at least one node"

    @FR-7
    Scenario: Delete removes the graph and its history
      Given a graph with triggers and an execution
      When the graph is deleted
      Then the response is 204, the list is empty, its triggers are gone, and the execution's runs stay on their task
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: Disabling a trigger clears its next occurrence
      Given a graph with an enabled schedule trigger
      When the trigger is disabled
      Then next_run_at is null and the trigger and its cron text are kept

    @FR-8
    Scenario: Renaming keeps a pending occurrence
      Given a graph with a schedule trigger whose next occurrence is set
      When only the graph's name changes
      Then the trigger's next_run_at is unchanged
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: A due trigger fires once
      Given a graph with an enabled schedule trigger whose next_run_at passed
      When the scheduler ticks twice
      Then exactly one execution with trigger "schedule" and that trigger's id started
      And the trigger's occurrence moved into the future
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: Running creates a grouping task
      When a graph named "chain" is run
      Then the response is 201 and a task titled "[Graph] chain" exists with the execution's runs

    @FR-10
    Scenario: A second run while one is in flight is refused
      Given a graph with a running execution
      When it is run again
      Then the response is 409
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: Downstream prompt renders the upstream answer
      Given a chain A -> B where B's prompt is "Second: {{draft}}"
      When A's run settles with answer "DRAFT TEXT"
      Then B's agent run is enqueued with prompt "Second: DRAFT TEXT"
      And the execution succeeds with A's output recorded in the state

    @FR-11
    Scenario: A run node links to the execution
      Given a running graph execution
      When the run node's agent run is read
      Then kind is "graph" and graph_execution_id and graph_node_id are set
    ```

- [ ] **FR-12**

    ```gherkin
    @FR-12
    Scenario: A cli node runs a command and feeds stdout downstream
      Given run -> cli -> run, where the command renders upstream output into its arguments
      When the chain runs and the command exits 0
      Then the cli node's output is the command's stdout and the downstream prompt contains it

    @FR-12
    Scenario: A failing command fails the node
      Given a cli node whose command exits 1
      When the chain runs
      Then the cli node fails with "exit 1" in its error and the downstream node is skipped
    ```

- [ ] **FR-13**

    ```gherkin
    @FR-13
    Scenario: Failure skips downstream
      Given a chain A -> B
      When A fails
      Then B is skipped with "An upstream node did not finish"
    ```

- [ ] **FR-14**

    ```gherkin
    @FR-14
    Scenario: The execution pauses on a form
      Given a chain run -> form -> run
      When the first run settles
      Then the execution detail reports a pending form with the declared fields and defaults

    @FR-14
    Scenario: An answer flows downstream
      Given a pending form with field f1
      When the form is answered with f1 = "yes"
      Then the downstream run is enqueued with prompt "Verdict: yes" and the answers are stored in the state
    ```

- [ ] **FR-15**

    ```gherkin
    @FR-15
    Scenario: An unused form is skipped
      Given a graph with a run node and a form with no edges
      When the run settles
      Then the execution succeeds and the form node is skipped

    @FR-15
    Scenario: Cancelling a form fails it
      Given a pending form
      When the form is cancelled
      Then the execution fails with the form marked failed and its downstream node skipped
    ```

- [ ] **FR-16**

    ```gherkin
    @FR-16
    Scenario: The execution settles
      Given a two-node chain where both runs succeed
      When the walk finishes
      Then the execution status is "succeeded" with empty error and both nodes are done
    ```

- [ ] **FR-17**

    ```gherkin
    @FR-17
    Scenario: Cancel a running execution
      Given a running execution with an active run
      When it is cancelled
      Then the response is 200 with status "cancelled" and the node is skipped
      And cancelling it again returns 409
    ```

- [ ] **FR-18**

    ```gherkin
    @FR-18
    Scenario: History lists across graphs
      Given two graphs that both ran
      When GET /api/graphs/executions is read
      Then every execution is listed newest first with its graph name

    @FR-18
    Scenario: Detail reports node outcomes from the live rows
      Given an execution whose run succeeded after its state was written
      When the execution detail is read
      Then the node's status reads done and its output is the run's answer
    ```

- [ ] **FR-19**

    ```gherkin
    @FR-19
    Scenario: A restart marks a lost execution failed
      Given an execution left in status running by a previous process
      When reconciliation runs
      Then the execution is failed with "restart" in the error and an ended_at timestamp
    ```

- [ ] **FR-20**

    ```gherkin
    @FR-20
    Scenario: The page shows both tabs
      When /graphs is opened
      Then the Graphs tab lists rows with their triggers, step count, and Run action, and the Executions tab lists rows

    @FR-20
    Scenario: The settings form edits the trigger list
      Given a graph with a schedule trigger
      When its settings are opened, a webhook trigger is added, and the form is saved
      Then the update carries both triggers and the list is refreshed

    @FR-20
    Scenario: The executions tab shows the pending form
      Given a running execution waiting on a form
      When its row is expanded
      Then the form dialog renders the fields and Submit stores the values while Cancel fails the form
    ```

- [ ] **FR-21**

    ```gherkin
    @FR-21
    Scenario: Run a graph from the CLI
      Given a saved graph
      When `agentic graphs run <id>` runs
      Then the CLI reports the started execution
    ```

- [ ] **FR-22**

    ```gherkin
    @FR-22
    Scenario: Triggers are typed rows
      When a graph is created with a schedule trigger and a webhook trigger
      Then each is stored with its type, config, and enabled flag
      And an unknown type or an invalid cron is refused with 400

    @FR-22
    Scenario: Saving the trigger list replaces it
      Given a graph with two triggers
      When the settings are saved with one of them
      Then the other is deleted and the kept trigger's pending occurrence survives
    ```

- [ ] **FR-23**

    ```gherkin
    @FR-23
    Scenario: A webhook starts the graph
      Given a graph with an enabled webhook trigger that has a secret
      When its fire URL is posted with the right X-Trigger-Secret header
      Then the response is 201 with trigger "webhook" and the execution starts
      And a missing or wrong secret, a disabled trigger, or a busy graph is refused
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: An answer written by the endpoint survives the executor's writes
      Given an execution whose executor holds a working state copy
      When the form endpoint stores answers and the executor next persists its state
      Then the stored form values are still present in the state
    ```

## Conflicts

None identified.

## Open Questions

None.
