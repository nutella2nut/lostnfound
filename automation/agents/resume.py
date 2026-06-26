"""Resume Claude Code after an answer is received.

Writes the answer to a file that Claude Code can read,
and optionally executes a resume command.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from automation import config
from automation.storage.models import Answer, Question

logger = logging.getLogger("automation.agents.resume")

ANSWER_DIR = config.STATE_DIR / "answers"


def write_answer_file(question: Question, answer: Answer) -> Path:
    """Write the answer to a JSON file for Claude Code to consume.

    Returns the path to the answer file.
    """
    ANSWER_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"answer_{question.id}.json"
    path = ANSWER_DIR / filename

    payload = {
        "question_id": question.id,
        "question": question.question,
        "question_type": question.question_type,
        "answer_text": answer.answer_text,
        "answer_option": answer.answer_option,
        "answered_by": answer.discord_username,
        "answered_at": answer.created_at,
        "project_slug": question.project_slug,
    }

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Answer file written: %s", path)
    return path


def write_resume_message(question: Question, answer: Answer) -> Path:
    """Write a plain-text resume message for Claude Code.

    This file can be piped into Claude Code or read by an agent.
    """
    ANSWER_DIR.mkdir(parents=True, exist_ok=True)
    path = ANSWER_DIR / "latest_answer.txt"

    if answer.answer_option:
        choice_line = f"Selected option: {answer.answer_option}"
    else:
        choice_line = "Freeform response"

    message = (
        f"--- Discord Response ---\n"
        f"Question: {question.question}\n"
        f"{choice_line}\n"
        f"Answer: {answer.answer_text}\n"
        f"Answered by: {answer.discord_username}\n"
        f"---\n"
        f"\n"
        f"The user has responded via Discord. "
        f"Please record this decision in DECISIONS.md if appropriate, "
        f"then continue with the next task.\n"
    )

    path.write_text(message, encoding="utf-8")
    logger.info("Resume message written: %s", path)
    return path


def trigger_resume(question: Question, answer: Answer) -> bool:
    """Attempt to resume Claude Code with the answer.

    Returns True if resume was triggered successfully.
    """
    if not config.RESUME_ENABLED:
        logger.info("Resume disabled — answer written to file only")
        return False

    answer_file = write_answer_file(question, answer)
    resume_msg_path = write_resume_message(question, answer)

    if config.RESUME_COMMAND:
        # Custom resume command — execute it with env vars pointing to answer files.
        try:
            env = {
                "ANSWER_FILE": str(answer_file),
                "RESUME_MESSAGE": str(resume_msg_path),
                "QUESTION_ID": str(question.id),
                "PROJECT_SLUG": question.project_slug,
            }
            result = subprocess.run(
                config.RESUME_COMMAND,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                env={**__import__("os").environ, **env},
            )
            if result.returncode == 0:
                logger.info("Resume command succeeded")
                return True
            else:
                logger.warning("Resume command failed: %s", result.stderr[:500])
                return False
        except subprocess.TimeoutExpired:
            logger.warning("Resume command timed out")
            return False
        except Exception:
            logger.exception("Resume command error")
            return False

    # Default: just write the files. Log the path so the user knows where to find it.
    logger.info(
        "Answer ready at %s — resume Claude Code with: "
        "cat %s",
        answer_file, resume_msg_path,
    )
    return True
