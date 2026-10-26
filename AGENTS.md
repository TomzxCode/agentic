<!-- sdlc-anchor begin -->
## SDLC

This project tracks features, requirements, specifications, and decisions under [`.sdlc/`](.sdlc/).

Before starting work on a feature:
- Read `.sdlc/context/` (`project-overview.md`, `architecture.md`, `conventions.md`, `vocabulary.md`, `schema.dbml`, `infrastructure.md`) for project context, and apply the style rules in `conventions.md` to anything you write.
- Run `/sdlc status` to see feature progress, or `/sdlc continue` to resume in-progress work.
- Run `/sync-sdlc` to reconcile `.sdlc/` with the current codebase.

Never commit local-only state: `.sdlc/state.yml`, `.sdlc/features/*/progress.md`, and `status-report.html`.
<!-- sdlc-anchor end -->

## UI conventions

- Product and UI rules live in `.sdlc/context/conventions.md` (the "Frontend and UI" section), not in this file. Read that section before changing the frontend, and record a new UI decision there instead of growing this file.

<!-- pdlc-anchor begin -->
## PDLC

This project tracks product initiatives, from discovery through launch and measurement, under [`.pdlc/`](.pdlc/).

Before starting work on an initiative:
- Read `.pdlc/context/` (`product-overview.md`, `vision.md`, `goals.md`) for product context, and apply the style rules found there to anything you write.
- Run `/pdlc status` to see initiative progress, or `/pdlc continue` to resume in-progress work.

Every phase transition runs a proceed/pivot/kill gate via `/make-decision`. Never commit local-only state: `.pdlc/state.yml` and `.pdlc/initiatives/*/progress.md`.
<!-- pdlc-anchor end -->
