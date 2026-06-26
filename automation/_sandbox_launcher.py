"""Sandbox launcher: redirect state to a writable /tmp dir before launching the bot.

The cowork-mounted filesystem doesn't support SQLite locking, so we redirect
all runtime state to /tmp/lafstate. This is only needed when running the bot
inside the sandbox; on the host (macOS), `python -m automation` works directly.
"""
from __future__ import annotations

from pathlib import Path

# Patch config paths BEFORE anything else imports them.
_STATE = Path("/tmp/lafstate")
_STATE.mkdir(parents=True, exist_ok=True)

from automation import config  # noqa: E402
config.STATE_DIR = _STATE
config.DB_PATH = _STATE / "questions.db"
config.HANDOFF_ARCHIVE_DIR = _STATE / "handoffs"

print(f"[launcher] STATE_DIR redirected to {_STATE}")

from automation.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
