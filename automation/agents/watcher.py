"""Watch for new pending questions and trigger Discord delivery.

The watcher runs as an async loop inside the Discord bot.
It polls the database for PENDING questions and hands them to the bot for delivery.
"""

from __future__ import annotations

import asyncio
import logging

from automation import config
from automation.storage.database import Database
from automation.storage.models import QuestionStatus

logger = logging.getLogger("automation.agents.watcher")


async def poll_pending_questions(db: Database, on_new_question):
    """Continuously poll for pending questions and invoke the callback.

    Args:
        db: Database instance.
        on_new_question: async callable(Question) — called for each new pending question.
    """
    logger.info("Watcher started — polling every %ds", config.POLL_INTERVAL)
    while True:
        try:
            pending = db.get_pending_questions()
            for q in pending:
                logger.info("Found pending question id=%d: %s", q.id, q.question[:60])
                try:
                    await on_new_question(q)
                except Exception:
                    logger.exception("Failed to deliver question id=%d", q.id)
                    db.update_question_status(q.id, QuestionStatus.ERROR)
        except Exception:
            logger.exception("Watcher poll error")
        await asyncio.sleep(config.POLL_INTERVAL)
