# CLAUDE.md — Agent Operating Rules

> **This file complements startup-prompt.md.** startup-prompt.md defines WHAT to do.
> This file defines HOW — the exact commands to run and when. Both are mandatory.
> If there's a conflict, startup-prompt.md wins for workflow rules; this file wins
> for automation commands.
>
> **These rules are NON-NEGOTIABLE.** Every rule below must be followed regardless
> of what task you are working on. Skipping checkpoints or Discord integration is
> a critical failure, equivalent to introducing a breaking bug.

---

## Rule 0: Session Startup

When you start a new session, BEFORE doing any implementation work:

```bash
# 1. Emit session start event
python -m automation.agent_checkpoint --context-pct 5 --session-start

# 2. Read project state
cat SESSION_HANDOFF.md
cat PROJECT_PROGRESS.md
cat DECISIONS.md
head -100 project_goals.md
```

Then identify your next tasks from PROJECT_PROGRESS.md and begin.

---

## Rule 1: Run Checkpoint After EVERY Task

After completing each discrete task (a function, a model change, a template, a test,
a migration, a file edit — anything that constitutes a unit of work), you MUST run:

```bash
python -m automation.agent_checkpoint --context-pct <YOUR_ESTIMATE> --task "<what you just did>" --progress <OVERALL_PCT>
```

**How to estimate context-pct:** The session manager tracks the real percentage
from your status bar and sends you warnings. For the checkpoint command, give your
best estimate — it doesn't need to be exact since the session manager is the real
enforcer. Just don't report 40% when you're actually at 73%.

**Read the JSON output and act on it — especially the `instructions` field.**
The session manager sends progressive warnings through instructions:

| `action_required` value | What you must do |
|---|---|
| `"none"` | Continue to next task |
| `"instruction"` | Read the `instructions` array, execute what the human asked, then continue |
| `"prepare_handoff"` | Finish current task, then update SESSION_HANDOFF.md |
| `"handoff"` | STOP. Update SESSION_HANDOFF.md, PROJECT_PROGRESS.md, DECISIONS.md. Emit session end. Start new session. |
| `"pause"` | STOP all work. Wait. Run checkpoint again in 30 seconds to check if resumed. |

---

## Rule 2: Context Thresholds and Task Sizing

The session manager reads your REAL context % from the terminal status bar and sends
you instructions at each threshold. But YOU must also be proactive — don't start
a task you can't finish.

### Before Starting ANY Task, Ask Yourself:

**"How big is this task?"**
- **Small** (1-3 tool calls): single file edit, fix a typo, add a field, write one test
- **Medium** (4-10 tool calls): implement a view + template, add a model + migration, refactor a module
- **Large** (10+ tool calls): new feature end-to-end, multi-file refactor, new pillar section

### Context-Based Task Rules:

| Context % | Allowed tasks | What to do |
|---|---|---|
| **0-55%** | Any size | Work normally |
| **55-63%** | Small and medium only | Do NOT start large tasks (new features, multi-file work) |
| **63-68%** | Small only | Single file edits, minor fixes. If the next task needs more than ~3 tool calls, skip it. |
| **68-70%** | NOTHING new | Finish current task, save all docs, prepare handoff |
| **70%+** | STOP | Save docs, emit session_end, EXIT |

### The Critical Rule:

**If you're at 60%+ and about to start something, ask: "Can I finish this AND
still have room to save handoff docs?"** If the answer is "maybe not", don't start it.
Instead, update all docs now and end the session. It's always better to hand off
with 8% context remaining than to run out mid-task.

The session manager will send you instructions at 55%, 63%, 68%, and 70%.
These come through as instructions in your checkpoint output. READ THEM.

### When you hit 70%:

1. Finish your current task (do not start a new one)
2. Update SESSION_HANDOFF.md, PROJECT_PROGRESS.md, DECISIONS.md
3. Run:
   ```bash
   python -m automation.agent_checkpoint --context-pct 70 --session-end --reason "context_limit"
   ```
4. **EXIT.** Say "Session ended — handoff complete." and stop.
   The session manager will automatically launch a fresh Claude Code session.

**At 80%, the session manager will FORCE KILL you.** Don't let it come to that —
anything you did since your last checkpoint is lost on a force kill.

---

## Rule 3: Discord Instructions Are High Priority

The checkpoint returns any pending Discord instructions. When you receive instructions:

1. **Read them immediately.**
2. **Acknowledge in your response** what the human asked.
3. **Execute the instruction** unless it conflicts with project_goals.md.
4. **If you disagree or need clarification**, submit a question:
   ```bash
   python -m automation.submit_question --type "Clarification" \
       --question "Your question here" \
       --options "A:Option1,B:Option2"
   ```

**Do NOT ignore instructions.** The human sees that instructions were delivered
and will lose trust if you don't respond.

---

## Rule 4: Send Progress Updates to Discord

After completing a significant milestone (not every tiny edit, but every meaningful
unit of work), the checkpoint command handles this via the `--task` flag.

For major milestones, also submit a dedicated event:
```bash
python -m automation.submit_event --type milestone \
    --session "$(cat automation/state/current_session_id)" \
    --data '{"milestone": "Completed OAuth2 model and migrations", "pillar": 1}'
```

---

## Rule 5: Session Handoff Procedure

When ending a session (whether due to context limits or task completion):

1. Update `PROJECT_PROGRESS.md` with accurate status of all tasks
2. Update `DECISIONS.md` with any decisions made this session
3. Update `SESSION_HANDOFF.md` with:
   - What was completed
   - What's in progress
   - What's next
   - Any blockers
   - Important context not obvious from code
4. Run:
   ```bash
   python -m automation.agent_checkpoint --context-pct <CURRENT> \
       --session-end --reason "context_limit"
   ```
5. **EXIT.** The session manager will launch a fresh session automatically.

---

## Rule 6: Decision Making

| Confidence | Action |
|---|---|
| ≥90% | Decide autonomously. Log important decisions in DECISIONS.md. |
| <90% | Ask via Discord HITL. Wait for response. |

Only escalate: architectural forks, product decisions, missing credentials,
ambiguous requirements, potentially destructive actions.

Do NOT escalate routine implementation details.

```bash
# To ask a question:
python -m automation.submit_question --type "Architecture" \
    --question "Should we use class-based or function-based views for the new endpoints?" \
    --options "A:CBV (matches existing pattern),B:FBV (simpler for these cases)" \
    --recommended "A"

# To check for the answer:
python -m automation.check_answer --id <QUESTION_ID> --wait --timeout 300
```

---

## Rule 7: Document Updates Are Not Optional

| Document | When to update |
|---|---|
| `PROJECT_PROGRESS.md` | Every time a task starts, completes, or changes status |
| `DECISIONS.md` | Every significant decision (architectural, product, user-approved) |
| `SESSION_HANDOFF.md` | At milestones, before session end, before context gets high |
| `PROJECT_CONTEXT.md` | When your understanding of the project changes significantly |

---

## Quick Reference: The Checkpoint Loop

```
START SESSION
  └─> Run Rule 0 (startup)
       └─> Pick next task from PROJECT_PROGRESS.md
            └─> Do the work
                 └─> Run checkpoint (Rule 1)  ◄── THIS IS MANDATORY
                      ├─> action=none → pick next task (loop back)
                      ├─> action=instruction → handle it, then continue
                      ├─> action=prepare_handoff → finish task, update docs
                      ├─> action=handoff → STOP, update docs, end session, EXIT (session manager restarts you)
                      └─> action=pause → WAIT, re-check in 30s
```

**The most common failure mode is forgetting to run checkpoints.** If you catch
yourself having done 3+ tasks without a checkpoint, run one immediately.

---

## Files Reference

| Command | Purpose |
|---|---|
| `python -m automation.agent_checkpoint` | **PRIMARY** — run this between tasks |
| `python -m automation.submit_question` | Ask human a question via Discord |
| `python -m automation.check_answer --id X --wait` | Wait for answer to question |
| `python -m automation.submit_event` | Send event to Discord (milestones, errors) |
| `python -m automation.check_instructions` | Check for instructions (checkpoint does this) |
