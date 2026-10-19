# How to read the review queue

## Problem

Your review skills write their reports to disk, and you want one place that shows which pull requests still need your review and what each review step concluded.

## Prerequisites

- A running API and the web app open (see the [tutorial](../tutorials/getting-started.md)).
- At least one pull request with review reports in the store.
  Run `/review-pr-full` (or the individual review skills) on a PR to write them.
- `ghx` on your `PATH`: the queue reads each pull request's own fields (title, state, author, age) from it.

The reports live under `AGENTIC_SDLC_DIR` (`~/.sdlc` by default), at `{owner}/{repository}/pull-requests/`.

## Steps

1. Open the **Review queue** page (the `/reviews` route).
   Each row is one pull request with review reports in the store, grouped by repository, newest first.

   ![The Review queue, one row per pull request, grouped by repository, with a merge-readiness light and a column per review step](../assets/reviews.png)

2. Read the row's own columns: the pull request number and title, its author, its age, the last comment and who made it, the commit last reviewed, and when the last review ran.
   Click the number to open the pull request on GitHub.
3. Read the merge-readiness light beside the number:
   - 🟢 green: the collected signals could be approved automatically.
   - 🟡 yellow: something still needs attention.
   - 🔴 red: a signal blocks approval.
4. Read the per-step columns, one per review skill: **Behavior**, **Risk**, **Coverage**, **Validate**, **Verify**, and **Review**.
   A cell shows the step's verdict (a mark when it has one, otherwise the verdict word), and a report that does not cover the newest reviewed commit shows the commit it covers in red underneath.
   A step with no report shows a dash.
5. Click a cell to open that step's report.
6. Use the row's **📝** to open the linked task in its PR view, or **➕** to import the pull request into a new task, the same as the repository view's **New task**.
7. Use **Share** to pick the must/should/may findings the skills recorded and hand the selection to an agent run on the task, whose skills post them to the pull request.
   The app itself posts nothing to GitHub.
8. Click **Refresh** to re-read the store and bypass the short cache of the pull request field lookups.

## Where the data comes from

The review-step state comes from the reports the review skills write under the store, and each pull request's own fields come from `ghx`.
Fields that would need a read the queue does not make (the diff size, the approvers, the pull requests an open PR blocks) are left out.

## Verification

Every PR with a report in the store appears, its readiness light reflects its step verdicts, and clicking a step cell opens that report.

## Related

- [Run an agent against a task](../how-to/run-an-agent.md) to act on a pull request through its task's PR view.
- [HTTP API reference](../reference/http-api.md) covers the `/api/reviews` endpoints.
- [Configuration reference](../reference/configuration.md) lists `AGENTIC_SDLC_DIR`.
