# Startup Instructions

Read and obey the following files in order:

1. PROJECT_GOALS.md
2. PROJECT_CONTEXT.md
3. PROJECT_PROGRESS.md
4. DECISIONS.md
5. SESSION_HANDOFF.md
6. implementer-agent.md
7. reviewer-agent.md

If PROJECT_PROGRESS.md, DECISIONS.md, or SESSION_HANDOFF.md do not exist, create them before beginning any implementation work.

---

## Required Workflow

### Implementation Role

Assume the role defined in implementer-agent.md while performing implementation work.

### Review Role

Use reviewer-agent.md as an independent review checklist before considering any task complete.

For every meaningful implementation milestone:

1. Complete the implementation.
2. Review the work against reviewer-agent.md.
3. Fix any issues discovered during review.
4. Verify the implementation works.
5. Update PROJECT_PROGRESS.md.
6. Update DECISIONS.md if any non-obvious technical, architectural, or product decision was made.
7. Update SESSION_HANDOFF.md if stopping, compacting, switching milestones, or waiting for input.

---

## Project Analysis Before Coding

Before making any code changes:

1. Analyze the current codebase.
2. Determine which goals are already completed.
3. Determine which goals are partially completed.
4. Determine which goals remain.
5. Review prior decisions.
6. Produce a prioritized execution plan.
7. Begin work on the highest-priority unfinished item.

Do not re-plan the entire project if a valid plan already exists. Continue from the next unfinished task whenever possible.

---

## Discord Human-in-the-Loop (HITL)

Before asking a new Discord question:

1. Check DECISIONS.md.
2. Check previously answered questions.
3. Check existing project documentation.
4. Estimate confidence in the decision.

Decision rule:

* If confidence is 90% or higher, make the decision and continue.
* If confidence is below 90%, escalate through Discord using the HITL workflow.

Only escalate when:

* A business decision is required.
* Multiple valid approaches exist and confidence is below 90%.
* Credentials, secrets, permissions, or external approvals are required.
* Requirements are genuinely ambiguous.

Do not ask duplicate questions that have already been answered.

All blockers requiring human input must use the Discord workflow.

---

## Project Documentation Rules

### PROJECT_PROGRESS.md

* Update immediately when work starts, completes, or changes status.
* Keep it as the source of truth for project status.
* Never rewrite the file from scratch.
* Only modify the relevant sections.

### DECISIONS.md

* Record all significant non-obvious decisions.
* Record important user decisions.
* Record Discord HITL decisions.
* Never remove historical decisions.
* Append new decisions instead.

### SESSION_HANDOFF.md

Update whenever:

* A milestone completes.
* A major task completes.
* Waiting for user input.
* Waiting for Discord input.
* Preparing for compaction.
* Ending a work session.

The handoff must clearly state:

* What was completed.
* Current work in progress.
* Next actions.
* Known blockers.
* Important context not obvious from the codebase.

### PROJECT_CONTEXT.md

* Keep PROJECT_CONTEXT.md current with environment, configuration, and operational context that future sessions will need.
* Update it whenever environment variables, credentials references, deployment targets, integrations, or external service configurations change.
* Do not duplicate content from PROJECT_GOALS.md or PROJECT_PROGRESS.md here — this file is for runtime/operational context only.

---

## Context Management

Target maximum context utilization: **70%**.

Update the Discord dashboard context percentage at approximately **25%, 40%, 50%, 60%, 65%, and 70%** estimated context usage. This is mandatory — the dashboard relies on these checkpoints, and skipping them is the most common reason the Discord status appears stale.

Threshold actions:

* **60%** — Finish the current logical unit of work. Do not start any major new feature past this point.
* **65%** — Update PROJECT_PROGRESS.md, DECISIONS.md, SESSION_HANDOFF.md, and any relevant PROJECT_CONTEXT.md entries. These updates must be committed before crossing 70%.
* **70%** — Stop all implementation work. Complete any remaining documentation updates. Perform a final re-scan of PROJECT_GOALS.md. Then follow the Compaction and Session Restart procedure below.

If a Discord dashboard update fails or no Discord channel is configured, log the attempt locally (in SESSION_HANDOFF.md under a `Context Updates` subsection) and continue — never block implementation on a failed dashboard update, but never silently skip the checkpoint either.

---

## Compaction and Session Restart

Before compaction:

1. Finish the current logical stopping point.
2. Update PROJECT_PROGRESS.md.
3. Update DECISIONS.md.
4. Update SESSION_HANDOFF.md.

After compaction or session restart:

1. Read SESSION_HANDOFF.md.
2. Read PROJECT_PROGRESS.md.
3. Re-scan PROJECT_GOALS.md.
4. Read DECISIONS.md.
5. Verify the codebase matches the recorded state.
6. Continue from the next unfinished task.

Do not restart planning from scratch unless the project requirements have changed.

---

## Execution Policy

Continue working autonomously until one of the following occurs:

* Human input is required.
* Discord HITL input is required.
* Credentials are required.
* External approvals are required.
* The project is complete.
* Context utilization reaches the 70% threshold (see Context Management).

When blocked, stop at the smallest reasonable decision point, document the state, and use the Discord HITL workflow.
