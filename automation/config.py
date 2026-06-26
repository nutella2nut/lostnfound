"""Configuration loaded from environment variables."""

import os
import re
from pathlib import Path

# Paths
AUTOMATION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = AUTOMATION_DIR.parent
STATE_DIR = AUTOMATION_DIR / "state"
DB_PATH = STATE_DIR / "questions.db"

# Project identity — derived from the project root folder name.
_raw_name = PROJECT_ROOT.name  # e.g. "LostAndFoundSystem"


def _slug(name: str) -> str:
    """Convert CamelCase/PascalCase/mixed name to a Discord-safe channel slug.

    Examples:
        LostAndFoundSystem -> lost-and-found-system
        Locl               -> locl
        ThreeJSSandpile    -> threejs-sandpile
    """
    # Insert hyphens before uppercase runs: "LostAndFound" -> "Lost-And-Found"
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name)
    # Handle consecutive uppercase: "ThreeJSSandpile" -> "ThreeJS-Sandpile" -> "Three-JS-Sandpile"
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", s)
    # Replace non-alphanumeric with hyphens, collapse, strip, lowercase
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-").lower()
    return s or "project"


PROJECT_SLUG = _slug(_raw_name)

# Key project documents
DECISIONS_MD = PROJECT_ROOT / "DECISIONS.md"
PROJECT_GOALS_MD = PROJECT_ROOT / "project_goals.md"
PROJECT_PROGRESS_MD = PROJECT_ROOT / "PROJECT_PROGRESS.md"
SESSION_HANDOFF_MD = PROJECT_ROOT / "SESSION_HANDOFF.md"
PROJECT_CONTEXT_MD = PROJECT_ROOT / "PROJECT_CONTEXT.md"

# Discord
DISCORD_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "")  # Required
DISCORD_CATEGORY_NAME = os.environ.get("DISCORD_CATEGORY_NAME", "claude-projects")
DASHBOARD_CHANNEL_NAME = os.environ.get("DASHBOARD_CHANNEL_NAME", "claude-dashboard")

# Context thresholds (percentage of context window used)
CONTEXT_THRESHOLD_CHECKPOINT = 50
CONTEXT_THRESHOLD_HANDOFF = 60
CONTEXT_THRESHOLD_WRAPUP = 70

# Resume
RESUME_ENABLED = os.environ.get("RESUME_ENABLED", "true").lower() == "true"
RESUME_COMMAND = os.environ.get("RESUME_COMMAND", "")  # Optional override

# Logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# Question polling interval (seconds)
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "3"))

# Dashboard update rate limit (seconds)
DASHBOARD_UPDATE_INTERVAL = int(os.environ.get("DASHBOARD_UPDATE_INTERVAL", "5"))

# Handoff archive directory
HANDOFF_ARCHIVE_DIR = STATE_DIR / "handoffs"
