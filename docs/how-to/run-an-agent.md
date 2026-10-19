# How to run an agent against a task

## Problem

You want a coding agent to work on a task, and you want to see and keep what it did.

## Prerequisites

- A running API and worker, and at least one ACP harness on your `PATH` (see the [tutorial](../tutorials/getting-started.md)).
- A task, and ideally a worktree so the agent has an isolated checkout.

## Steps

1. Open **Settings → Agent harnesses** and choose the harness the runs should use.
   Marking a harness as default makes it the one a task picks when it names none.
   Set a model on the harness to select it over ACP, or leave the model blank to use the harness's own default.
2. Create a worktree for the task if you have not already, so the agent works outside your main checkout.
   See [Create and remove worktrees](../how-to/use-worktrees.md).
3. Open the task's **Agent** panel, type a prompt, and run it.
   The run is enqueued, and the worker picks it up.

   ![A task page with the Agent panel below the description, context, notes, and worktrees](../assets/task.png)

4. Watch the transcript stream into the panel.
   You can cancel a run that is going the wrong way.
5. When you want a fresh summary and next-steps list, click **Refresh with agent** in the **Context** panel.
   This is a special run that reads the task and its items and writes the summary and next steps.

## Reopen a session later

When a run has a session id, the task shows links to reopen it:

- **Open in OpenChamber** opens your configured OpenChamber URL with the session id.
- **Open in terminal** opens your configured terminal URL template.
- **Copy resume command** copies a command such as `cd <worktree> && opencode --session <id>`.

For a session Agentic did not start, attach it by hand so it gets the same links:

```bash
agentic session add <task> ses_abc123 --cwd /path/to/checkout --label "repro"
```

Configure the link URLs in [Configure session links](../how-to/configure-session-links.md).

## Verification

The task's **Agent** panel lists the run with its transcript, and the session links open the recorded session.

## Related

- [How agents are wired](../explanation/how-agents-are-wired.md) explains the queue and the ACP harness abstraction.
- [CLI reference](../reference/cli.md) for `agentic run create`, `agentic run wait`, `agentic run stream`, and `agentic context refresh`.
