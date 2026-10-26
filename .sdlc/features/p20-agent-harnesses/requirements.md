---
title: "Agent harnesses and model selection"
status: done
---

# Requirements: Agent harnesses and model selection

## Overview

Agentic drives external coding agents over the Agent Client Protocol (ACP), and a harness is the stored description of one agent: the command to spawn, its arguments and environment, how to resume one of its sessions in a terminal, and where its own default model is configured.
This feature lets a user manage harnesses (seeded presets for OpenCode, OpenCode v2, and pi), pick the default one, and choose a model per harness or per run.
A harness's model choices live only on a live ACP session, so the API holds one warm session for the default harness to answer the model picker quickly.
A run selects its model over ACP after the session exists, never through a command-line flag, and a harness that cannot select a model produces a warning rather than a failed run.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| Task author | Picks the harness and model a run uses, and sees which model answered |
| Operator | Configures harness commands, resume commands, models, and the default in Settings or the CLI |

## Functional Requirements

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall seed the built-in harness presets (`opencode`, `opencode2`, `pi`) with their command, args, resume command, and default model source, and shall insert missing presets without overwriting existing rows. |
| FR-2 | Must | The system shall keep exactly one default harness, picked once (preferring `opencode2` when it is on PATH, else `opencode`), never overwriting a default the user chose or one outside the OpenCode family. |
| FR-3 | Must | The system shall create, list, update, and delete harnesses through the API and the CLI, reporting for each whether its command is on PATH. |
| FR-4 | Must | The system shall keep at most one default harness: promoting a harness demotes every other. |
| FR-5 | Must | Deleting a harness shall detach it from tasks, runs, and recorded sessions instead of deleting them. |
| FR-6 | Must | A run shall select its session model with the ACP `session/set_config_option` request on the `model` config option, after the session is created or resumed, never through a harness command-line flag. |
| FR-7 | Must | A model chosen for one run shall take precedence over the harness's configured model, and an empty choice shall leave the model to the harness. |
| FR-8 | Should | When a harness exposes no model option or rejects the requested value, the system shall emit a warning into the run's transcript and continue the run with the harness's own default. |
| FR-9 | Should | A run shall record the model the session answers with (`model`) and the harness's own label for it (`model_name`), resolved as the selected model, else the model reported for the session, else the requested model. |
| FR-10 | Must | The system shall expose each harness's model choices, answered from the warm session held for the default harness or from a short-lived session for any other harness, with a `live` flag and an `error` reason when the harness cannot be asked. |
| FR-11 | Should | The API shall hold one warm ACP session for the default harness for introspection only, reopen it when the harness's id, command, args, model, or env changes, and retry failures with exponential backoff; `AGENTIC_WARM_HARNESS_SESSION=0` shall disable it. |
| FR-12 | Should | The system shall display, for each harness, the model its own config file names (via `default_model_source`), read only for display. |
| FR-13 | Should | The Settings page shall edit a harness's command, args, resume command, and model, and the task view's run panel shall offer a harness picker and a model picker with a "Harness default" option. |
| FR-14 | Should | The CLI shall offer `agentic harness list`, `create`, `update`, and `delete`. |

## Non-Functional Requirements

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Must | Performance | Default model resolution shall spawn no harness process and shall reject config files larger than 1 MB, so listing harnesses stays fast. |
| NFR-2 | Must | Availability | A harness that cannot start shall never prevent the API from serving; the pool retries with backoff (5 s initial, 300 s cap) and the models endpoint returns the reason. |
| NFR-3 | Must | Reliability | A model selection failure shall not fail the run. |
| NFR-4 | Should | Security | Spawned harness processes shall run with `AGENTIC_ACTOR=agent` so CLI calls they make are attributed to an agent. |
| NFR-5 | Should | Testability | The backend test suite shall run with `AGENTIC_WARM_HARNESS_SESSION=0`, so no test spawns an ACP harness process. |

## Constraints

- Model choices can only be read from a live ACP session; there is no offline model registry.
- `opencode acp` rejects `--model` as an unknown flag, so a model can never be passed as a harness argument.
- The default model display reads the harness's user-level config file only; project-level config in a run's working directory is not visible.

## Acceptance Criteria

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Built-in presets are seeded once
      Given an empty harness table
      When harnesses are seeded
      Then the opencode, opencode2, and pi presets exist with their commands, resume commands, and default model sources
      And seeding again changes no existing row
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: The default harness is picked once
      Given opencode2 is on PATH and no harness is default
      When harnesses are seeded
      Then opencode2 is the only default harness and the harness_default_seeded marker is set
      When the user sets opencode as default and seeding runs again
      Then opencode stays the default
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: The harness list reports availability
      Given a harness whose command is not on PATH
      When the harness list is read
      Then the harness is listed with available false and a reason naming the missing command
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Promoting a harness demotes the others
      Given two harnesses with opencode2 as the default
      When opencode is updated with is_default true
      Then opencode is the only default harness
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Deleting a harness detaches its users
      Given a harness used by a task, a run, and a recorded session
      When the harness is deleted
      Then the task, run, and session remain with no harness id
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: The model is applied over ACP after the session exists
      Given a harness with model "zai-coding-plan/glm-5.3"
      When a run starts
      Then the runner creates or resumes the session first and then sends session/set_config_option for the model option
      And the harness command line carries no model flag
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: A per-run model wins over the harness model
      Given a harness with model "a/b" and a run with requested_model "c/d"
      When the run applies its model
      Then the session is asked for "c/d"
    ```

    ```gherkin
    @FR-7
    Scenario: No model leaves the choice to the harness
      Given a run with no requested model on a harness with no model
      When the run applies its model
      Then no set_config_option request is sent
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: A harness without a model option only warns
      Given a harness that exposes no model config option
      When a run with a model starts
      Then a warning event is published to the transcript
      And the run continues with the harness's own default and does not fail
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: The run records the model that answered
      Given a session that reports model "zai/glm" with the harness label "GLM 5.3"
      When the run finishes its model selection
      Then the run stores model "zai/glm" and model_name "GLM 5.3"
      And the transcript carries a model event naming the model or its label
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: Model choices come from a live session
      Given the default harness's warm session is up
      When its models are requested
      Then the choices are returned with live true
      When a non-default harness's models are requested twice
      Then the first request opens a short-lived session and the second reuses the cached answer
      When the harness cannot be asked
      Then the response carries an empty list and the error reason
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: The warm session follows the default harness
      Given the API is running with the warm session enabled
      When the default harness's command changes
      Then the held session is reopened for the new fingerprint
      When AGENTIC_WARM_HARNESS_SESSION is 0
      Then no session is held and models come from on-demand sessions
    ```

- [ ] **FR-12**

    ```gherkin
    @FR-12
    Scenario: The harness's own default model is displayed
      Given a harness whose default_model_source points at a config file naming a model
      When the harness is read
      Then default_model shows that model
      When the file is missing or larger than 1 MB
      Then default_model is null and nothing is guessed
    ```

- [ ] **FR-13**

    ```gherkin
    @FR-13
    Scenario: The harness and model pickers in the task view
      Given a task with at least one harness
      When the run panel is opened
      Then the harness picker lists the harnesses with availability and marks the default
      And the model picker lists the selected harness's models with a "Harness default" option
      And the Settings page saves a model per harness on blur
    ```

- [ ] **FR-14**

    ```gherkin
    @FR-14
    Scenario: CLI harness commands
      Given a running API
      When agentic harness list, create, update, and delete run
      Then each prints the outcome and the harness table reflects it
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Default model resolution spawns nothing
      Given a harness with a default_model_source
      When the model is resolved
      Then no harness process is started
      And a config file over 1 MB resolves to no model
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: A broken harness does not take the API down
      Given the default harness's command fails to start
      When the pool tries to hold a session
      Then the API keeps serving and retries with backoff capped at 300 s
      And the models endpoint reports the failure reason
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: A rejected model does not fail the run
      Given a harness that rejects the requested model value
      When the run applies the model
      Then the run continues with a warning and completes normally
    ```

- [ ] **NFR-4**

    ```gherkin
    @NFR-4
    Scenario: Spawned harnesses are marked as agents
      Given a harness process spawned for a run
      Then its environment contains AGENTIC_ACTOR=agent merged over the harness's own env
    ```

- [ ] **NFR-5**

    ```gherkin
    @NFR-5
    Scenario: Tests never spawn a harness
      Given the backend test suite runs
      Then AGENTIC_WARM_HARNESS_SESSION is 0 and no ACP process is spawned
    ```

## Conflicts

None identified.

## Open Questions

None. The implemented code answers every question this document raises.
