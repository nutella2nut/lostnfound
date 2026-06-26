#!/usr/bin/env python3
"""Entry point: python -m automation

Starts the Discord bot with question polling and answer handling.
"""

from __future__ import annotations

import logging
import sys

from automation import config
from automation.discord_bot.bot import ClaudeProjectBot
from automation.storage.database import Database


def main():
    # Configure logging.
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("automation")

    # Validate config.
    if not config.DISCORD_TOKEN:
        logger.error("DISCORD_BOT_TOKEN is not set. See automation/README.md for setup.")
        sys.exit(1)

    logger.info("Project: %s (slug: %s)", config.PROJECT_ROOT.name, config.PROJECT_SLUG)
    logger.info("Database: %s", config.DB_PATH)
    logger.info("DECISIONS.md: %s", config.DECISIONS_MD)
    logger.info("Context thresholds: checkpoint=%d%% handoff=%d%% wrapup=%d%%",
                config.CONTEXT_THRESHOLD_CHECKPOINT,
                config.CONTEXT_THRESHOLD_HANDOFF,
                config.CONTEXT_THRESHOLD_WRAPUP)
    logger.info("Dashboard channel: %s", config.DASHBOARD_CHANNEL_NAME)

    # Initialize storage.
    db = Database(config.DB_PATH)

    # Log recovery state.
    pending = db.get_pending_questions()
    sent = db.get_sent_questions()
    if pending or sent:
        logger.info(
            "Recovery: %d pending, %d sent (awaiting answers) from previous session",
            len(pending), len(sent),
        )

    # Start bot.
    bot = ClaudeProjectBot(db)
    bot.run(config.DISCORD_TOKEN, log_handler=None)  # We configure logging ourselves.


if __name__ == "__main__":
    main()
