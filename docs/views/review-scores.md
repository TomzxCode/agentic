# Review scores

`/review-scores` charts the 0-1 score each review step records, one line per rubric, so you can see whether reviews are getting better or worse over time.

## Problem

A single review report says how one pull request did.
It does not show whether the code you send for review is improving, whether one repository is consistently harder, or whether one author's pull requests keep scoring below the rest.
This page turns the score every review step writes into its report marker into one daily series per rubric, then lets you narrow the series by repository and author.

## How to use it

### What a score means

Every review step writes a `score` between `0` and `1` into its report marker:

- `1.00`: the step's concern is fully addressed, with nothing to fix.
- `0.75`: the step found a should or may issue, so the concern passes with a gap.
- `0.25` or lower: a must issue or a blocking verdict.

The score comes from the step's findings and its overall light, using the formula in the review skills' shared conventions.
The marker keeps the value the step computed, so a later rubric change does not rewrite history.
The page reads the score from the marker; a report written before the marker carried a score is scored from its findings and verdict instead, so older history still appears.

### The rubrics

The charts follow the review steps in dispatch order, grouped the way the review chain runs them:

| Group           | Rubrics                            |
| --------------- | ---------------------------------- |
| Assessments     | Behavior, Risk, Adversarial        |
| Surface reviews | CLI, SDK, API, DB                  |
| Review chain    | Coverage, Validate, Verify, Review |

A surface review only runs when the diff touches its surface, so its chart stays empty for a pull request that does not.
A rubric with no scored review is left out rather than drawn as a flat zero.

### The filters

| Filter             | Behaviour                                                                                                     |
| ------------------ | ------------------------------------------------------------------------------------------------------------- |
| `All repositories` | A multi-select with a `Filter…` box and `Select all` / `Deselect all`. Nothing chosen means every repository. |
| `All authors`      | The same multi-select over the pull request authors.                                                          |
| `Clear filters`    | Appears once a repository or author is chosen and resets both.                                                |

Both choices are remembered on this device under `agentic.reviewScoreFilters`, so leaving and returning keeps them.
A repository or author that disappears from the store after a refresh is dropped from the selection.

### Reading a chart

The vertical axis is the score from `0` to `1`, with gridlines at each quarter.
The horizontal axis is real time: a gap between two days with reviews stays a gap rather than collapsing the points together.
A point is one day's average for that rubric; hover it to see the score and how many reviews it averaged.
The card header shows the rubric's mean over the shown runs, and the footer names the number of reviews and the latest score with its day.

A day with no run is not drawn as a zero, so a quiet week does not look like a bad one.

## CLI and agent interface

There is no `agentic` command for this page.

| Operation            | CLI  | HTTP                      |
| -------------------- | ---- | ------------------------- |
| Read the scored runs | none | `GET /api/reviews/scores` |

The skills' own `~/.agents/scripts/review_scores.py` reads the same markers and prints daily aggregates per skill on the command line, with `--date`, `--days`, `--skill`, `--repo`, and `--json`.
This page adds the per-repository and per-author filters and the per-rubric charts.

## Related

- [Review queue](reviews.md) for the current review state of each pull request.
- [Metrics](metrics.md) for the factory metrics (autonomy rate and yield) rather than review quality.
- [Configuration](../reference/configuration.md) for `AGENTIC_SDLC_DIR`, which sets the review store this page reads.
