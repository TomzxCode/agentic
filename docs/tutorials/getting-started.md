# Tutorial: set up Agentic and complete your first task

This tutorial takes you from an empty machine to a task with an agent-written summary and a completed agent run.
It assumes no prior knowledge of Agentic.

## What you will build

A running Agentic app on your own machine, one task that points at a registered repository, a git worktree for that task, and an agent run whose transcript streams into the app.

## Prerequisites

Install these first:

- Python 3.12 or newer.
- [uv](https://docs.astral.sh/uv/).
- Node.js 20 or newer.
- At least one ACP harness on your `PATH`, either `opencode` / `opencode2` or `pi-acp`.

Clone the repository and move into it:

```bash
git clone https://github.com/TomzxCode/agentic.git
cd agentic
```

## Step 1: install the backend and CLI

`uv sync` creates a virtual environment and installs the backend (`agentic-server`) and the CLI (`agentic`).

```bash
uv sync
```

## Step 2: install the frontend dependencies

```bash
cd frontend
pnpm install
cd ..
```

## Step 3: start the API

Open a terminal in the repository root and run:

```bash
uv run agentic-server serve --host 0.0.0.0 --port 8600 --reload
```

Leave this terminal running.

## Step 4: start the worker

Agent runs are executed by a worker, not by the API.
Open a second terminal in the repository root and run:

```bash
uv run agentic-server worker
```

Leave this terminal running too.
Without a worker, runs stay queued and never progress.

## Step 5: start the frontend

Open a third terminal in the repository root and run:

```bash
cd frontend
pnpm run dev
```

The Vite dev server proxies `/api` to the API on port 8600.

## Step 6: open the app

Open [http://localhost:5173](http://localhost:5173) in a browser.
You should see the task list with an empty sidebar.

![The task list, with status filters and upcoming deadlines across the top](../assets/tasks.png)

## Step 7: create a task

Click the `+` at the top of the sidebar.
Type a title such as `Add a health check endpoint` and save.
The task appears in the list and on the focus stack, because every open task is on the stack.

![The new-task form, with an optional field to import a GitHub issue, pull request, or Slack thread](../assets/new-task.png)

## Step 8: register a repository

Open **Repositories** in the sidebar and click **Browse**.
Pick a git repository on your machine that you want the agent to work in.
Select it and confirm.

## Step 9: create a worktree

Open your task and scroll to the **Worktrees** panel.
Click to create a worktree.
Agentic runs `git worktree add` and creates an isolated checkout under `~/.agentic/worktrees` by default.

The task now has a working directory the agent can use.

## Step 10: refresh the context with an agent

In the task's **Context** panel, click **Refresh with agent**.
Agentic sends the task, its items, and its worktrees to the default harness and asks for a summary and next steps.
When the run finishes, the task shows the summary and the next-steps list.

## Step 11: run an agent against the task

In the **Agent** panel, type a prompt such as `List the files in this repository and suggest where a health check endpoint should live`, then run it.
The transcript streams into the panel as the agent works.
When the run finishes, it is recorded against the task with links to reopen its session.

![A task page: header fields, description, agent-written context and next steps, notes, worktrees, and the agent panel](../assets/task.png)

## What you have learned

- Agentic runs as three processes: the API, a worker, and the frontend dev server.
- Tasks hold the context, and worktrees give the agent an isolated checkout.
- A context refresh writes the summary and next steps you read when you come back.
- Every agent run is queued, streamed, and recorded.

## Next steps

- Learn the moving parts in [Concepts](../explanation/concepts.md).
- Import real work instead of typing it, in [Import a GitHub issue or Slack thread](../how-to/import-work.md).
- Look up every command in the [CLI reference](../reference/cli.md).
