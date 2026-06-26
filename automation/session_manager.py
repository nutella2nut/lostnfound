#!/usr/bin/env python3
"""Session Manager — launches and auto-restarts Claude Code sessions.

Reads Claude Code's REAL context percentage from the terminal status bar
and triggers session handoff when it crosses 70%. No more guessing.

Usage:
    cd /path/to/LostAndFoundSystem
    python automation/session_manager.py

    # Custom context limit (default 70%):
    python automation/session_manager.py --context-limit 65

    # With time-based backup watchdog (default: no time limit):
    python automation/session_manager.py --max-minutes 25

    # Dry run:
    python automation/session_manager.py --dry-run
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AUTOMATION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = AUTOMATION_DIR.parent
STATE_DIR = AUTOMATION_DIR / "state"
EVENTS_FILE = STATE_DIR / "events.jsonl"
SESSION_END_SIGNAL = STATE_DIR / "session_ended"
SESSION_ID_FILE = STATE_DIR / "current_session_id"

DEFAULT_CONTEXT_LIMIT = 70

# Regex to match Claude Code's status bar: "73% [1 / 200k]" or "73%  [1 / 200k]"
CONTEXT_PCT_PATTERN = re.compile(r'(\d{1,3})%\s+\[')

STARTUP_PROMPT = """
You are resuming work on this project. Follow these steps EXACTLY:

1. Read CLAUDE.md (automation rules — mandatory, tells you the exact commands to run)
2. Read startup-prompt.md (workflow rules — mandatory)
3. Read SESSION_HANDOFF.md (what happened last session)
4. Read PROJECT_PROGRESS.md (current task status)
5. Read DECISIONS.md (decisions made so far)
6. Read implementer-agent.md and reviewer-agent.md (your roles)
7. Skim project_goals.md for overall context
8. Run your first checkpoint:
   python -m automation.agent_checkpoint --context-pct 5 --session-start
9. Pick up the next task from PROJECT_PROGRESS.md and begin working.

CRITICAL RULES:
- You MUST run `python -m automation.agent_checkpoint` after EVERY task.
  This is how you communicate with Discord, track context, and trigger session handoffs.
- At 70% context, you MUST save all docs, emit session_end, and EXIT.
  The session manager will restart you automatically with a clean context.
- Check the checkpoint output for Discord instructions from the human.
  Respond to them — the human can see that instructions were delivered.
Read CLAUDE.md for full details on all of these.
""".strip()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    # Write to stderr so it doesn't mix with Claude Code's TUI
    sys.stderr.write(f"\r[session-mgr {ts}] {msg}\n")
    sys.stderr.flush()


def clear_session_signals():
    for f in [SESSION_END_SIGNAL, SESSION_ID_FILE]:
        if f.exists():
            f.unlink()


def check_for_session_end() -> bool:
    return SESSION_END_SIGNAL.exists()


def write_emergency_instruction(message: str):
    instr_dir = STATE_DIR / "instructions"
    instr_dir.mkdir(parents=True, exist_ok=True)
    instr_id = f"instr_{uuid.uuid4().hex[:12]}"
    instr_data = {
        "id": instr_id,
        "instruction_text": message,
        "discord_username": "session-manager",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (instr_dir / f"{instr_id}.json").write_text(json.dumps(instr_data, indent=2))


def set_terminal_size(fd, rows, cols):
    """Set the terminal size of a pty."""
    size = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, size)


def get_terminal_size():
    """Get the current terminal size."""
    try:
        size = os.get_terminal_size()
        return size.lines, size.columns
    except OSError:
        return 24, 80


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes for cleaner parsing."""
    return re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)


# ---------------------------------------------------------------------------
# PTY-based Claude launcher with context monitoring
# ---------------------------------------------------------------------------

def run_claude_with_monitoring(
    prompt: str,
    context_limit: int,
    max_seconds: int | None,
) -> str:
    """Run Claude Code in a pty, monitor context %, return exit reason.

    Returns: "session_end", "context_limit", "process_exit", "watchdog", "interrupted"
    """
    # Create pseudo-terminal
    master_fd, slave_fd = pty.openpty()

    # Match terminal size
    rows, cols = get_terminal_size()
    set_terminal_size(master_fd, rows, cols)

    # Launch Claude Code
    cmd = [
        "claude",
        "--permission-mode", "bypassPermissions",
        prompt,
    ]

    proc = subprocess.Popen(
        cmd,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        cwd=str(PROJECT_ROOT),
        env={**os.environ, "CLAUDE_SESSION_MANAGED": "true"},
        close_fds=True,
    )
    os.close(slave_fd)

    # Save original terminal settings
    old_settings = None
    stdin_fd = sys.stdin.fileno()
    try:
        old_settings = termios.tcgetattr(stdin_fd)
        # Put terminal in raw mode so keystrokes pass through immediately
        import tty
        tty.setraw(stdin_fd)
    except termios.error:
        pass

    # Handle terminal resize
    def handle_resize(signum, frame):
        r, c = get_terminal_size()
        set_terminal_size(master_fd, r, c)
        # Forward SIGWINCH to child
        if proc.poll() is None:
            os.kill(proc.pid, signal.SIGWINCH)

    old_handler = signal.signal(signal.SIGWINCH, handle_resize)

    current_context_pct = 0
    warnings_sent = set()  # Track which warning levels we've sent
    start_time = time.time()
    exit_reason = "process_exit"
    parse_buffer = ""

    # Progressive warning thresholds relative to context_limit (default 70)
    # These are absolute percentages
    warn_levels = {
        context_limit - 15: (  # 55% — advisory
            "CONTEXT ADVISORY: You are at {pct}%. "
            "Do NOT start any large tasks (new features, big refactors). "
            "Only small/medium tasks from here."
        ),
        context_limit - 7: (  # 63% — caution
            "CONTEXT CAUTION: You are at {pct}%. "
            "Only start SMALL tasks (single file edits, minor fixes). "
            "If the next task looks like it needs more than ~3 tool calls, "
            "skip it and begin handoff instead."
        ),
        context_limit - 2: (  # 68% — prepare to stop
            "CONTEXT WARNING: You are at {pct}%. "
            "Do NOT start ANY new task. Finish what you're doing right now, then: "
            "1) Update SESSION_HANDOFF.md, PROJECT_PROGRESS.md, DECISIONS.md. "
            "2) Run: python -m automation.agent_checkpoint --context-pct {pct} "
            "--session-end --reason context_limit "
            "3) EXIT."
        ),
        context_limit: (  # 70% — stop now
            "CONTEXT LIMIT REACHED: {pct}%. STOP IMMEDIATELY. "
            "Do NOT write any more code. Save handoff docs and run: "
            "python -m automation.agent_checkpoint --context-pct {pct} "
            "--session-end --reason context_limit — Then EXIT."
        ),
    }

    try:
        while True:
            # Check if process exited
            if proc.poll() is not None:
                if check_for_session_end():
                    exit_reason = "session_end"
                else:
                    exit_reason = "process_exit"
                break

            # Check session_end signal
            if check_for_session_end():
                exit_reason = "session_end"
                break

            # Time-based watchdog (if configured)
            if max_seconds:
                elapsed = time.time() - start_time
                if elapsed >= max_seconds:
                    exit_reason = "watchdog"
                    break

            # Select on master (claude output) and stdin (user input)
            try:
                readable, _, _ = select.select([master_fd, stdin_fd], [], [], 0.5)
            except (OSError, ValueError):
                break

            for fd in readable:
                if fd == master_fd:
                    try:
                        data = os.read(master_fd, 4096)
                    except OSError:
                        data = b""
                    if not data:
                        exit_reason = "process_exit"
                        break
                    # Pass through to user's terminal
                    os.write(sys.stdout.fileno(), data)

                    # Parse for context percentage
                    text = data.decode("utf-8", errors="ignore")
                    parse_buffer += text
                    # Keep buffer manageable
                    if len(parse_buffer) > 2000:
                        parse_buffer = parse_buffer[-1000:]

                    clean = strip_ansi(parse_buffer)
                    matches = CONTEXT_PCT_PATTERN.findall(clean)
                    if matches:
                        latest_pct = int(matches[-1])
                        if latest_pct != current_context_pct:
                            current_context_pct = latest_pct
                            # Update context_level.json so Discord dashboard stays current
                            try:
                                ctx_file = STATE_DIR / "context_level.json"
                                ctx_file.write_text(json.dumps({
                                    "pct": current_context_pct,
                                    "session_id": "session-manager",
                                }))
                            except OSError:
                                pass

                        # Check progressive warning thresholds
                        for threshold, msg_template in sorted(warn_levels.items()):
                            if current_context_pct >= threshold and threshold not in warnings_sent:
                                label = {
                                    context_limit - 15: "ADVISORY",
                                    context_limit - 7: "CAUTION",
                                    context_limit - 2: "WARNING",
                                    context_limit: "LIMIT",
                                }.get(threshold, "ALERT")
                                log(f"Context {label}: {current_context_pct}% (threshold: {threshold}%)")
                                write_emergency_instruction(
                                    msg_template.format(pct=current_context_pct)
                                )
                                warnings_sent.add(threshold)

                        # Hard kill if way over limit
                        if current_context_pct >= context_limit + 10:
                            log(f"HARD LIMIT: {current_context_pct}% — forcing restart.")
                            exit_reason = "context_limit"
                            break

                elif fd == stdin_fd:
                    try:
                        data = os.read(stdin_fd, 4096)
                    except OSError:
                        data = b""
                    if data:
                        os.write(master_fd, data)
            else:
                continue
            break  # Inner break → outer break

    except KeyboardInterrupt:
        exit_reason = "interrupted"

    finally:
        # Restore terminal settings
        if old_settings:
            try:
                termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_settings)
            except termios.error:
                pass
        signal.signal(signal.SIGWINCH, old_handler)

        # Clean up process
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

        try:
            os.close(master_fd)
        except OSError:
            pass

    return exit_reason


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Auto-restart Claude Code sessions")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-sessions", type=int, default=0,
                        help="Max sessions before stopping (0=unlimited)")
    parser.add_argument("--context-limit", type=int, default=DEFAULT_CONTEXT_LIMIT,
                        help=f"Context %% to trigger handoff (default: {DEFAULT_CONTEXT_LIMIT})")
    parser.add_argument("--max-minutes", type=int, default=0,
                        help="Backup time limit per session in minutes (0=disabled)")
    parser.add_argument("--cooldown", type=int, default=5,
                        help="Seconds between sessions (default: 5)")
    args = parser.parse_args()

    max_seconds = args.max_minutes * 60 if args.max_minutes else None

    log(f"Session Manager starting for: {PROJECT_ROOT.name}")
    log(f"Context limit: {args.context_limit}%")
    if max_seconds:
        log(f"Backup time limit: {args.max_minutes} minutes")
    log(f"Permission mode: bypassPermissions")

    STATE_DIR.mkdir(parents=True, exist_ok=True)

    session_count = 0

    while True:
        session_count += 1

        if args.max_sessions and session_count > args.max_sessions:
            log(f"Reached max sessions ({args.max_sessions}). Stopping.")
            break

        log(f"=== SESSION {session_count} ===")
        clear_session_signals()

        if session_count == 1:
            prompt = STARTUP_PROMPT
        else:
            prompt = (
                "NEW SESSION after automatic handoff. "
                "Previous session ended due to context limits. "
                "Your handoff docs have been updated.\n\n"
                + STARTUP_PROMPT
            )

        if args.dry_run:
            log(f"DRY RUN — would launch claude with context limit {args.context_limit}%")
            break

        reason = run_claude_with_monitoring(prompt, args.context_limit, max_seconds)

        if reason == "interrupted":
            log("Interrupted by user (Ctrl+C).")
            break

        elif reason == "process_exit":
            log("Claude Code exited without session_end. Stopping.")
            break

        elif reason in ("session_end", "context_limit", "watchdog"):
            log(f"Session ended (reason: {reason}). Preparing next session...")

            time.sleep(2)

            restart_info = {
                "session_number": session_count + 1,
                "previous_ended_at": datetime.now(timezone.utc).isoformat(),
                "reason": reason,
            }
            (STATE_DIR / "last_restart.json").write_text(json.dumps(restart_info, indent=2))

            log(f"Cooling down {args.cooldown}s...")
            time.sleep(args.cooldown)
            log("Starting fresh session...")
            continue

    log("Session Manager stopped.")


if __name__ == "__main__":
    main()
