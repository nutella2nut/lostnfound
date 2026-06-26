#!/usr/bin/env python3
"""Agent checkpoint — run this between every task.

This is the SINGLE command Claude Code runs to handle all automation:
  - Report context level
  - Check for Discord instructions
  - Check pause state
  - Submit progress events
  - Determine if a session handoff is needed

Usage:
    # Basic checkpoint (report context, check instructions):
    python -m automation.agent_checkpoint --context-pct 45

    # With a progress update:
    python -m automation.agent_checkpoint --context-pct 55 \
        --task "Implemented OAuth model" --progress 30

    # Session start:
    python -m automation.agent_checkpoint --context-pct 5 --session-start

    # Session end (triggers handoff):
    python -m automation.agent_checkpoint --context-pct 68 --session-end \
        --reason "context_limit"

Output is always JSON so Claude Code can parse and act on it:
{
    "status": "ok",
    "context_pct": 55,
    "action_required": "none",          // or "pause", "handoff", "instruction"
    "instructions": [...],
    "is_paused": false,
    "threshold_crossed": null,           // or "checkpoint", "handoff", "wrapup"
    "message": "All clear. Continue working."
}
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure automation package is importable
_automation_dir = Path(__file__).resolve().parent
if str(_automation_dir.parent) not in sys.path:
    sys.path.insert(0, str(_automation_dir.parent))

from automation import config
from automation.providers.file import (
    FileContextProvider,
    FileEventProvider,
    FileInstructionProvider,
)
from automation.storage.models import AgentEvent, ContextLevel


def _get_session_id() -> str:
    """Read or create a persistent session ID for this agent run."""
    session_file = config.STATE_DIR / "current_session_id"
    if session_file.exists():
        return session_file.read_text().strip()
    sid = f"session-{uuid.uuid4().hex[:12]}"
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    session_file.write_text(sid)
    return sid


# Max checkpoints per session before forced handoff.
# Each task ≈ 5-10% context, so 10 checkpoints ≈ 50-100% context.
MAX_CHECKPOINTS_PER_SESSION = 10


def _get_and_increment_checkpoint_count() -> int:
    """Track how many checkpoints have been called this session. Returns the NEW count."""
    counter_file = config.STATE_DIR / "checkpoint_count"
    count = 0
    if counter_file.exists():
        try:
            count = int(counter_file.read_text().strip())
        except (ValueError, OSError):
            count = 0
    count += 1
    counter_file.write_text(str(count))
    return count


def main():
    parser = argparse.ArgumentParser(description="Agent checkpoint — run between tasks")
    parser.add_argument("--context-pct", type=int, required=True,
                        help="Current estimated context window usage (0-100)")
    parser.add_argument("--task", type=str, default=None,
                        help="Description of task just completed (triggers progress event)")
    parser.add_argument("--progress", type=int, default=None,
                        help="Overall project progress percentage (0-100)")
    parser.add_argument("--session-start", action="store_true",
                        help="Emit session_start event")
    parser.add_argument("--session-end", action="store_true",
                        help="Emit session_end event")
    parser.add_argument("--reason", type=str, default="",
                        help="Reason for session end (e.g. context_limit)")
    args = parser.parse_args()

    config.STATE_DIR.mkdir(parents=True, exist_ok=True)

    session_id = _get_session_id()
    ctx_provider = FileContextProvider(config.STATE_DIR)
    event_provider = FileEventProvider(config.STATE_DIR)
    instr_provider = FileInstructionProvider(config.STATE_DIR)

    result = {
        "status": "ok",
        "session_id": session_id,
        "context_pct": args.context_pct,
        "action_required": "none",
        "instructions": [],
        "is_paused": False,
        "threshold_crossed": None,
        "message": "",
    }

    # --- 1. Update context level ---
    ctx_provider.write_level(ContextLevel(pct=args.context_pct, session_id=session_id))

    # --- 1b. Track checkpoint count ---
    checkpoint_num = _get_and_increment_checkpoint_count() if not args.session_start else 0
    if args.session_start:
        # Reset counter on new session
        counter_file = config.STATE_DIR / "checkpoint_count"
        counter_file.write_text("0")
        checkpoint_num = 0

    result["checkpoint_number"] = checkpoint_num

    # --- 2. Check thresholds (checkpoint count OR self-reported %) ---
    pct = args.context_pct
    forced_by_count = (
        checkpoint_num >= MAX_CHECKPOINTS_PER_SESSION
        and not args.session_start
        and not args.session_end
    )

    if forced_by_count:
        result["threshold_crossed"] = "wrapup"
        result["action_required"] = "handoff"
        result["message"] = (
            f"CHECKPOINT LIMIT REACHED ({checkpoint_num}/{MAX_CHECKPOINTS_PER_SESSION}). "
            "You have done enough work this session — context is likely high. "
            "STOP new tasks. Update SESSION_HANDOFF.md, PROJECT_PROGRESS.md, "
            "DECISIONS.md. Then emit session_end and EXIT."
        )
    elif pct >= config.CONTEXT_THRESHOLD_WRAPUP:  # 70
        result["threshold_crossed"] = "wrapup"
        result["action_required"] = "handoff"
        result["message"] = (
            f"CONTEXT AT {pct}% — at or above wrapup threshold "
            f"({config.CONTEXT_THRESHOLD_WRAPUP}%). "
            "STOP new tasks. Update SESSION_HANDOFF.md, PROJECT_PROGRESS.md, "
            "DECISIONS.md. Then emit session_end and EXIT."
        )
    elif pct >= config.CONTEXT_THRESHOLD_HANDOFF:  # 60
        result["threshold_crossed"] = "handoff"
        result["action_required"] = "prepare_handoff"
        result["message"] = (
            f"Context at {pct}% — approaching limit. "
            "Update SESSION_HANDOFF.md, PROJECT_PROGRESS.md, DECISIONS.md. "
            "Finish current task only, do NOT start new features."
        )
    elif pct >= config.CONTEXT_THRESHOLD_CHECKPOINT:  # 50
        result["threshold_crossed"] = "checkpoint"
        result["message"] = (
            f"Context at {pct}% — checkpoint. Continue working, "
            "but be mindful of context limits."
        )
    else:
        result["message"] = f"Context at {pct}%. All clear, continue working."

    # --- 3. Check pause state ---
    if instr_provider.is_paused():
        result["is_paused"] = True
        result["action_required"] = "pause"
        result["message"] = "PAUSED by human via Discord. Wait for /resume."

    # --- 4. Check for instructions ---
    pending = instr_provider.check_pending()
    if pending:
        result["instructions"] = []
        for instr in pending:
            result["instructions"].append({
                "id": instr.id,
                "from": instr.discord_username,
                "text": instr.instruction_text,
                "time": instr.created_at,
            })
            instr_provider.acknowledge(instr.id)
        if result["action_required"] == "none":
            result["action_required"] = "instruction"
        result["message"] += (
            f" {len(pending)} instruction(s) from Discord — read and act on them."
        )

    # --- 5. Emit events ---
    if args.session_start:
        event_provider.emit(AgentEvent(
            type="session_start",
            session_id=session_id,
            data={"started_at": datetime.now(timezone.utc).isoformat()},
        ))

    if args.session_end:
        event_provider.emit(AgentEvent(
            type="session_end",
            session_id=session_id,
            data={
                "reason": args.reason or "manual",
                "final_pct": args.context_pct,
                "ended_at": datetime.now(timezone.utc).isoformat(),
            },
        ))
        # Write signal file for session_manager.py to detect
        signal_file = config.STATE_DIR / "session_ended"
        signal_file.write_text(json.dumps({
            "session_id": session_id,
            "reason": args.reason or "manual",
            "final_pct": args.context_pct,
            "ended_at": datetime.now(timezone.utc).isoformat(),
        }))
        # Clear session ID so next run gets a fresh one
        session_file = config.STATE_DIR / "current_session_id"
        if session_file.exists():
            session_file.unlink()
        # Clear checkpoint counter
        counter_file = config.STATE_DIR / "checkpoint_count"
        if counter_file.exists():
            counter_file.unlink()

    if args.task:
        event_provider.emit(AgentEvent(
            type="progress_update",
            session_id=session_id,
            data={
                "task": args.task,
                "progress_pct": args.progress or 0,
                "context_pct": args.context_pct,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        ))

    # --- Output ---
    print(json.dumps(result, indent=2))

    # Exit code signals action needed (0=continue, 1=action required)
    if result["action_required"] in ("handoff", "pause"):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
