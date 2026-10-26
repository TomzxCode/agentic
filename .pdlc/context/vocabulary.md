# Vocabulary

Product and domain terms used across `.pdlc/`.
The full domain and technical glossary lives in [`.sdlc/context/vocabulary.md`](../../.sdlc/context/vocabulary.md); this table carries the terms product conversations use most, with the product-level meaning.

| Term | Definition | Notes |
|---|---|---|
| Task | The unit of work everything hangs off: sources, worktrees, runs, summary, next steps. | Central entity; SDLC features hang off it too. |
| Item | Something external associated to tasks: Slack thread, GitHub issue or PR, Drive doc, URL, note, commit, or local path. | Also called a source item. |
| Focus stack | The ordered queue of in-flight tasks; the top one is current. | Parked tasks are off it and return automatically. |
| Parked | A task off the stack because it waits on a person or is snoozed. | Returns when the deferral ends. |
| Context refresh | An agent run that rewrites a task's summary and next steps. | The mechanism behind the resume-in-a-minute promise. |
| Agent run | One prompt to a harness in a working directory, with a live persisted transcript. | Runs over ACP; queued and executed by a worker. |
| Harness | A coding-agent command reachable over ACP, stored as a row. | OpenCode and pi are preconfigured. |
| Change | A recorded unit of factory output with a lifecycle and a human-intervened flag. | The input all factory metrics are computed from. |
| Autonomy rate | Share of accepted changes with no human intervention. | Success metric SM-2. |
| Yield | Share of accepted changes that survived their observation window without a revert. | Success metric SM-3. |
| Touchless | A change with no recorded human intervention. | The numerator of autonomy rate. |
| Metric baseline | The stored value a metric's trend is measured against. | Direction: improving, worsening, flat, or no-baseline. |
| Inbox | The triage queue of PR reviewer-feedback items and review SLO flags. | Decisions: implement, decline, defer. |
| Review SLO | How long a pull request may await review before the inbox flags it. | |
| Person | An individual a task or item involves, with aliases for de-duplication across sources. | |
| Initiative | A product opportunity moving through the PDLC phases under `.pdlc/initiatives/`. | ID format INIT-N; distinct from an SDLC feature (FEAT-N). |
| Gate | A proceed / pivot / kill decision that ends every PDLC phase. | Recorded under `.pdlc/decisions/`. |
