<!-- session_link: http://localhost:10000/?session=ses_ed778bb8affeJQ6f9Tkxe4MjUl -->
# Architecture

## System Overview

Agentic is a three-part app: a FastAPI backend that owns the database and agent execution, a Vue 3 single-page app that the backend serves, and an HTTP client CLI.
The backend drives coding agents over ACP (Agent Client Protocol) as child processes and streams normalized events to the SPA over SSE.

```mermaid
flowchart LR
    subgraph Client
        SPA["Vue 3 SPA (PWA)"]
        CLI["agentic CLI"]
    end
    subgraph Backend["FastAPI (agentic-server)"]
        API["HTTP + SSE API"]
        BUS["In-process event bus"]
        ACP["ACP client"]
    end
    DB[("SQLite\n~/.agentic/agentic.db")]
    Harness["ACP harness\n(opencode acp / pi-acp)"]
    Ext["ghx/git/slackx\n(GitHub, Slack, URLs)"]

    SPA -- "REST + SSE" --> API
    CLI -- "REST" --> API
    API --> DB
    API --> BUS
    ACP -- "JSON-RPC stdio" --> Harness
    API --> ACP
    API -- "subprocess" --> Ext
    BUS -- "SSE" --> SPA
```

## Entity Relationship Diagram

```mermaid
erDiagram
    TASK ||--o{ ASSOCIATION : "has"
    SOURCEITEM ||--o{ ASSOCIATION : "linked via"
    TASK ||--o{ WORKTREE : "owns"
    REPOSITORY ||--o{ WORKTREE : "hosts"
    TASK ||--o{ AGENTRUN : "runs"
    HARNESS ||--o{ AGENTRUN : "executes"
    AGENTRUN ||--o{ AGENTEVENT : "streams"
    TASK ||--o{ TIMELINEEVENT : "records"
    REPOSITORYGROUP ||--o{ REPOSITORYGROUPMEMBER : "contains"
    REPOSITORY ||--o{ REPOSITORYGROUPMEMBER : "belongs to"
    TASK ||--o{ TASKREPOSITORY : "draws on"
    REPOSITORY ||--o{ TASKREPOSITORY : "referenced by"
    REPOSITORYGROUP ||--o{ TASK : "scopes"
    HARNESS ||--o{ TASK : "default for"
    WORKTREE ||--o{ AGENTRUN : "runs in"
    TASK ||--o{ CHANGE : "produces"
    CHANGE ||--o{ CHANGEINTERVENTION : "records"
    REPOSITORY ||--o{ CHANGE : "touched by"
    WORKTREE ||--o{ CHANGE : "produced in"

    TASK {
        string id PK
        string title
        string description
        string status
        int priority
        json tags
        string group_id FK
        string harness_id FK
        string summary
        json next_steps
        datetime context_updated_at
    }
    SOURCEITEM {
        string id PK
        string source
        string kind
        string title
        string url
        string external_id
        json metadata_json
        string content
        datetime fetched_at
    }
    ASSOCIATION {
        string id PK
        string task_id FK
        string item_id FK
        string note
    }
    REPOSITORY {
        string id PK
        string name
        string path
        string remote_url
        string default_branch
    }
    REPOSITORYGROUP {
        string id PK
        string name
        string description
    }
    REPOSITORYGROUPMEMBER {
        string id PK
        string group_id FK
        string repository_id FK
    }
    TASKREPOSITORY {
        string id PK
        string task_id FK
        string repository_id FK
    }
    WORKTREE {
        string id PK
        string task_id FK
        string repository_id FK
        string branch
        string path
        string status
    }
    HARNESS {
        string id PK
        string name
        string command
        json args
        json env
        string model
        string resume_command
        bool is_default
    }
    AGENTRUN {
        string id PK
        string task_id FK
        string harness_id FK
        string worktree_id FK
        string cwd
        string prompt
        string kind
        string status
        string session_id
    }
    AGENTEVENT {
        int id PK
        string run_id FK
        int seq
        string type
        string text
        json data_json
    }
    TIMELINEEVENT {
        string id PK
        string task_id FK
        string type
        string message
        json data_json
    }
    SETTING {
        string key PK
        string value
    }
    CHANGE {
        string id PK
        string task_id FK
        string title
        string change_class
        string status
        string repository_id FK
        string worktree_id FK
        string external_ref
        bool human_intervened
        int intervention_count
        datetime opened_at
        datetime verified_at
        datetime accepted_at
        datetime closed_at
    }
    CHANGEINTERVENTION {
        string id PK
        string change_id FK
        string kind
        string note
    }
    METRICBASELINE {
        string metric PK
        float value
        int window_days
        int observation_days
        string note
        datetime captured_at
    }
```

The full schema with types, constraints, and indexes lives in [`schema.dbml`](schema.dbml).

## Key Components

| Component | Responsibility | Technology |
|---|---|---|
| HTTP API | REST endpoints and SSE streams for all resources | FastAPI, Pydantic/SQLModel |
| Persistence | Tables, engine, and in-place migrations | SQLite, SQLModel/SQLAlchemy |
| ACP client | Spawn a harness, normalize its updates, auto-approve permissions | `agent-client-protocol`, asyncio |
| In-process event bus | Publish run and task events to SSE subscribers | asyncio queues |
| Source services | Parse/infer/fetch items, build the context prompt, parse agent JSON | httpx, subprocess (`ghx`, `slackx`) |
| Git services | Create/remove worktrees, detect remote and default branch | `git` subprocess |
| Gantt view | Tasks as time bars with one marker per timeline event | `routers/gantt.py`, Vue GanttView |
| Change lifecycle | Record changes and the human interventions on them, from a task page | `routers/changes.py`, Vue ChangesPanel |
| Metrics engine | Compute autonomy rate and yield from changes, read against a baseline | `metrics.py`, `routers/metrics.py`, Vue MetricsView |
| Session links | Build OpenChamber/terminal/resume-command links from settings | templating over stored settings |
| SPA | Mobile-friendly task list, task detail, settings, live transcript, PWA install | Vue 3, Vite, vue-router, vite-plugin-pwa |
| User CLI | Scriptable client over the HTTP API | cyclopts, httpx, rich |
| Backend CLI | Run the server and report config | cyclopts, uvicorn |

## Data Flow

1. The SPA or CLI calls a REST endpoint on the backend.
2. The router reads or writes rows through SQLModel and writes a `TimelineEvent` for meaningful task changes.
3. Task changes are published on the in-process bus and streamed to any subscribed SPA as SSE (`/api/tasks/{id}/stream`).
4. An agent run spawns the selected harness as a child process, drives it over ACP JSON-RPC on stdio, normalizes each update into an `AgentEvent` (persisted and streamed on `/api/runs/{id}/stream`), then terminates the process.
5. A context refresh runs the same path, then parses a JSON `{summary, next_steps}` out of the assistant text and writes it back onto the task.

## Infrastructure

The app runs as a single local process plus the `git` and optional `ghx`/`slackx` binaries it shells out to.
There is no hosted environment and no CI.
Detailed stack, tooling, environments, deployment, and rollback live in [`infrastructure.md`](infrastructure.md); logging lives in [`observability.md`](observability.md).

## Architecture Decisions

- SQLModel over SQLite with PRAGMA WAL and foreign keys on, using small in-place migrations instead of a migration framework.
- ACP over stdio as the single agent abstraction, so a harness is a database row (command plus args) and never special-cased in code.
- An in-process asyncio event bus rather than an external broker, because the app is single-process and local.
- The SPA is built into `backend/static` and served by the API, so one process serves both the API and the UI.
