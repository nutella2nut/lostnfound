"""Parse structured question blocks from agent output.

Agents emit blocks ending with WAITING_FOR_DISCORD_REPLY.
This module extracts the structured fields into a Question object.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from automation.storage.models import Question

logger = logging.getLogger("automation.agents.parser")

# Matches lines like "QUESTION_TYPE: Business" — captures key and value.
_FIELD_RE = re.compile(r"^([A-Z_]+):\s*(.+)$", re.MULTILINE)

# Matches option blocks: "A:\n<text>" or "A: <text>"
_OPTION_RE = re.compile(
    r"^([A-Z]):\s*\n?\s*(.+?)(?=\n[A-Z]:\s|\nRECOMMENDED|\nRATIONALE|\nEXPECTED|\nCONFIDENCE|\nCHECKED|\nWAITING|\Z)",
    re.MULTILINE | re.DOTALL,
)

# The sentinel that signals a question is ready.
SENTINEL = "WAITING_FOR_DISCORD_REPLY"


def contains_question(text: str) -> bool:
    """Return True if the text contains a WAITING_FOR_DISCORD_REPLY block."""
    return SENTINEL in text


def parse_question(text: str, project_slug: str = "") -> Optional[Question]:
    """Parse a structured question block from agent output.

    Returns a Question object or None if parsing fails.
    """
    if SENTINEL not in text:
        return None

    # Extract the block: everything from the first recognized field up to SENTINEL.
    # Walk backward from SENTINEL to find the start of the block.
    sentinel_idx = text.index(SENTINEL)
    block_text = text[:sentinel_idx].rstrip()

    # Find the start of the structured block — look for QUESTION_TYPE or QUESTION:
    start_markers = ["QUESTION_TYPE:", "QUESTION:"]
    block_start = len(block_text)
    for marker in start_markers:
        idx = block_text.rfind(marker)
        if idx != -1 and idx < block_start:
            block_start = idx

    if block_start >= len(block_text):
        logger.warning("Could not find question block start in text")
        return None

    block = block_text[block_start:]

    # Extract simple key-value fields.
    fields: dict[str, str] = {}
    for m in _FIELD_RE.finditer(block):
        key = m.group(1).strip()
        val = m.group(2).strip()
        if key not in ("OPTIONS", "A", "B", "C", "D", "E"):
            fields[key] = val

    # Extract options.
    options_start = block.find("OPTIONS:")
    options_end = len(block)
    for end_marker in ("RECOMMENDED:", "RATIONALE:", "EXPECTED_IMPACT:", "CONFIDENCE:", "CHECKED_DECISIONS_MD:"):
        idx = block.find(end_marker, options_start + 1 if options_start != -1 else 0)
        if idx != -1 and idx < options_end and idx > (options_start or 0):
            options_end = idx

    options_block = block[options_start:options_end] if options_start != -1 else ""
    options_list = []
    for m in _OPTION_RE.finditer(options_block):
        label = m.group(1).strip()
        text_val = m.group(2).strip()
        if text_val:
            options_list.append({"label": label, "text": text_val})

    q = Question(
        project_slug=project_slug,
        question_type=fields.get("QUESTION_TYPE", ""),
        question=fields.get("QUESTION", ""),
        context=fields.get("CONTEXT", ""),
        options=json.dumps(options_list) if options_list else "[]",
        recommended=fields.get("RECOMMENDED", ""),
        rationale=fields.get("RATIONALE", ""),
        expected_impact=fields.get("EXPECTED_IMPACT", fields.get("EXPECTED", "")),
        confidence=fields.get("CONFIDENCE", ""),
        raw_block=block + "\n" + SENTINEL,
    )

    if not q.question:
        logger.warning("Parsed block but QUESTION field was empty")
        return None

    logger.info("Parsed question: type=%s q=%s", q.question_type, q.question[:80])
    return q
