# How to read the review queue

## Problem

You want one place that shows which pull requests still need your review and what each review step concluded, whether or not a review has run against a pull request yet.

## Prerequisites

- A running API and the web app open (see the [tutorial](../tutorials/getting-started.md)).
- `ghx` on your `PATH`: the queue reads each pull request's own fields (title, state, author, age) from it, the review scan searches its cache, and a pull request item's reviewer list comes from it too.
- The repositories you want scanned cached by `ghx` (run `ghx cache --repo owner/name` once for each): the scan reads that cache, not GitHub directly.
- Review reports in the store for the pull requests you have already reviewed.
  Run `/review-pr-full` (or the individual review skills) on a PR to write them.

The reports live under `AGENTIC_SDLC_DIR` (`~/.sdlc` by default), at `{owner}/{repository}/pull-requests/`.

## Steps

1. Open the **Review queue** page (the `/reviews` route).
   Each row is one pull request: those with review reports in the store, plus the ones the review scan found awaiting your review. Grouped by repository, newest first.

   ![The Review queue, one row per pull request, grouped by repository, with a merge-readiness light and a column per review step](../assets/reviews.png)

2. Filter the queue. By default it shows only **open** pull requests; a pull request whose state could not be read is treated as open.
   The status chips (**Open**, **Merged**, **Closed**, **All**) each carry a count over the whole queue, and the header totals follow what the filter shows.
   The **Drafts**, **Approved**, and **Reviewed** chips each carry a count over the whole queue and step through three states on click: **hidden**, **only** (keep just that kind), and **all** (keep everything); the chip shows its current state.
   Drafts and approved pull requests start **hidden**, since neither waits for a review; pull requests you already reviewed start **all**, since they may still need a follow-up.
   When one of them hides the only matching rows, the empty state says how many are hidden and offers to include them.
   When only one kind is shown and nothing matches, the empty state offers to show every pull request.
   Use the **All repositories** dropdown to pick one or more repositories; type in its filter box to narrow the list, and each choice toggles on and off.
   With nothing chosen it shows every repository, and the queue keeps only the rows of the chosen ones.
   Use the **All authors** dropdown the same way to pick one or more authors.
   At the top of either list, **Select all** takes every option the filter box currently lists and **Deselect all** clears the choice.
   Type in the search box to narrow by repository, number, title, or author.
   The status, drafts, repository, author, and search filters are remembered on this device, so leaving the page and coming back keeps them.
   When nothing matches, the empty state offers to clear the search, repositories, or author, or show all statuses.
3. Read the row's own columns: the pull request number and title, its author, its age, the last comment and who made it, the commit last reviewed, and when the last review ran.
   Click the number to open the pull request on GitHub.
   A **✅** after the number means GitHub has already approved the pull request (the reviews its branch requires are in), so it needs no further review from you.
   A **📨** means a review is requested from you, and **👀** means you already reviewed the pull request and it is still open.
4. Read the merge-readiness light beside the number:
   - 🟢 green: the collected signals could be approved automatically.
   - 🟡 yellow: something still needs attention.
   - 🔴 red: a signal blocks approval.
5. Read the per-step columns, one per review step: **Behavior**, **Risk**, **Adversarial**, **Coverage**, **Validate**, **Verify**, and **Review**.
   A cell shows the step's verdict (a mark when it has one, otherwise the verdict word), and a report that does not cover the newest reviewed commit shows the commit it covers in red underneath.
   A step that is running right now shows a spinner instead, and its tooltip says when it started; the spinner appears even before the step has written a report.
   A step with no report shows a dash.
   **Surfaces** folds the four conditional surface reviews into one cell: one token per surface that ran (**CLI**, **SDK**, **API**, **DB**) with its verdict, each opening its own report.
   A surface the diff did not touch leaves no token and is not counted as stale.
6. Click a cell to open that step's report.
   The PR view (a task's PR mode or the pull request page) shows a `Description` / `Review` / `Reports` switch under the pull request's title: `Reports` lists one tab per step that wrote a report, and clicking a step cell there opens it in that pane.
7. Use the row's **📝** to open the linked task in its PR view, or **➕** to import the pull request into a new task, the same as the repository view's **New task**.
8. Use **Share** to pick the must/should/may findings the skills recorded and hand the selection to an agent run on the task, whose skills post them inline on the pull request (one review comment per finding, on the file and line it is about).
   Each check or uncheck writes your decision (`include` or `skip`) onto that finding in its skill's state file, so the selection is still there when you come back.
   The app itself posts nothing to GitHub.
9. Click **Refresh** to re-read the store and bypass the short cache of the pull request field lookups.

## Where the pull requests come from

The review scan asks GitHub which pull requests await your review: the ones with a review requested from you (`review-requested:@me`), and the open ones you have already reviewed (`reviewed-by:@me`).
Discovery runs through `ghx`'s cache: the scan searches what `ghx` has cached, so a repository it has never cached is not searched.
A pull request the scan finds joins the queue even before any review report exists for it.

Configure the scan under **Settings → Review requests**:

- **How often to scan** is a duration such as `30m`, `1h`, or `1d`; leave it blank to stop scanning.
- **Review SLO** is a duration such as `8h` or `1d`: a pull request the scan has seen awaiting your review longer than that appears in the inbox. The wait starts when the scan first sees it waiting, and leaving the field blank turns the SLO off.
- **Review nudge SLO** is a duration such as `1h30m` or `1d` for your own pull requests: one that has waited that long since it was opened without any review from anyone (a comment review counts, the author's own does not) appears in the inbox with a `Poke reviewers` button that DMs each requested reviewer on Slack. Leaving the field blank turns the nudge off. This read does not go through the scan: it uses the same read as the [My PRs](../views/my-pulls.md) page, over the registered GitHub repositories.
- **Repositories with no policy of their own** is what a repository that has no policy of its own does: **Include** (scan every repository except the excluded ones) or **Exclude** (scan only the repositories marked include).
- Each repository can be left on **Default** to follow that choice, or set to **Include** or **Exclude** on its own.
- **Scan now** runs one pass immediately.

The section shows when the scan last ran, how many it found and kept, and any error.

## Request a review from a reviewer

Open a pull request item: from a row's **📝** in the queue, a task's PR view, or the Resources list.
Its **Description** tab lists the reviewers under the author line: the ones who already reviewed (with their latest state and when they last reviewed), and the ones a review is still requested from, shown as **Awaiting review**.
The standalone pull request page (opened from a repository's issue and PR grid) shows the same list on its Description tab.

Click the **👉** beside a reviewer to send them a Slack DM asking for their review.
The message reads `:wave::robot_face: I would love your review on this PR: <title linking to GitHub>`.

The GitHub login resolves through the People directory: the person carrying that login as an alias supplies the Slack user id (or Slack handle) among their other aliases.
When either is missing, the app says which one to add instead of sending.

The send needs `SLACK_TOKEN` in the environment or the `.env` file the server starts from, plus `SLACK_COOKIE` when the token is an `xoxc-` web token.
Without it, the poke reports that Slack is not configured.

## Where the data comes from

The review-step state comes from the reports the review skills write under the store, and each pull request's own fields come from `ghx`.
A pull request's GitHub review decision (which is what the **✅** approval mark reads) comes from `ghx` too, falling back to the store's `gh-pr-view.md` cache when `ghx` cannot answer.
A pull request item's reviewer list comes from `ghx` as well, from the reviews and review requests it caches for the pull request.
Fields that would need a read the queue does not make (the diff size, the pull requests an open PR blocks) are left out.

## Verification

Every PR with a report in the store appears (unless a kind filter hides it, which its chip changes), plus the ones the scan found awaiting your review, its readiness light reflects its step verdicts, and clicking a step cell opens that report.

## Related

- [Triage reviewer feedback](../how-to/triage-pr-feedback.md) to decide on the comments reviewers left.
- [Run an agent against a task](../how-to/run-an-agent.md) to act on a pull request through its task's PR view.
- [HTTP API reference](../reference/http-api.md) covers the `/api/reviews` endpoints.
- [Configuration reference](../reference/configuration.md) lists `AGENTIC_SDLC_DIR` and the `AGENTIC_REVIEW_SCAN_*` keys.
