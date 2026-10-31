# How to triage reviewer feedback

## Problem

Reviewers left comments on the pull requests you authored, and you want one place to read what each comment asks for and decide which to implement, which to decline, and which to defer, without opening every thread.

## Prerequisites

- A running API and the web app open (see the [tutorial](../tutorials/getting-started.md)).
- Reviewer-feedback analysis files in the store.
  Run `/handle-pr-reviewer-feedback` on a pull request you authored to write them.
- `ghx` available when the page re-reads each pull request's state.

The analysis files live under `AGENTIC_SDLC_DIR` (`~/.sdlc` by default), at `{owner}/{repository}/pull-requests/{number}/feedback/`.

## Steps

1. Open the **PR feedback** page (the `/feedback` route).
   Each card is one reviewer comment the analysis produced, grouped by pull request and newest first by default.

2. Read the card's pills: the **recommendation** (`implement`, `reject`, `clarify`, or `no-action`), its **confidence**, the comment **type**, whether the pull request is **closed**, the **decision status**, and the **run state**.

3. Read the card's sections, the first one open:
   - **Comment** is the reviewer's comment, with a **Thread** link to it.
   - **Analysis** is what the agent made of it.
   - **Recommended action** is what the agent suggests you do.
   - **Suggested reply** is a reply you can send back; press **copy** to take it.
   - **Suggested change** is the edit the agent proposes, when the comment asks for a code change.

4. Pick a decision:
   - **Implement**: you accept the comment and want the work done.
   - **Decline**: you reject it and want a reply that says so.
   - **Defer**: you accept it but not now.
   - **Reset**: clear the decision and return the card to pending.

   The app writes the decision into the analysis file's frontmatter and stamps when you decided.

5. Use the toolbar to narrow the list: search by title, author, repository, or id; filter by pull request state, repository, author, status, recommendation, or execution state; group by pull request, repository, author, recommendation, status, or comment type; and sort within each group.

6. Press **Refresh** to re-read the store and each pull request's state from GitHub.

## What a decision does

- A decision changes the card's status pill.
- Any decision queues the work: the card shows **awaiting run** until `/handle-pr-reviewer-feedback` carries the decision out.
  A **Defer** is carried out as a no-op that just marks it done.
- Decisions live in the analysis file's `decision` and `decided_at` keys.
  The executor stamps `executed_at` when it runs the decision, which is what turns **awaiting run** into **executed**.
- The app itself changes nothing on GitHub.
  It records the decision; the skill does the implement, the reply, or the resolve.

## Verification

Every analyzed comment appears as a card, a decision changes its status pill, and a recorded decision stays **awaiting run** until the executor runs it.

## Related

- [Read the review queue](../how-to/review-pull-requests.md) to see the pull requests these comments came from.
- [HTTP API reference](../reference/http-api.md) covers the `/api/feedback` endpoints.
- [Configuration reference](../reference/configuration.md) lists `AGENTIC_SDLC_DIR`.
