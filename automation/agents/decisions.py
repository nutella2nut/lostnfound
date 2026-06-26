"""Read and write DECISIONS.md."""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

from automation import config

logger = logging.getLogger("automation.agents.decisions")

# Section headers in DECISIONS.md
SECTIONS = [
    "Business Decisions",
    "Product Decisions",
    "Technical Decisions",
    "UI/UX Decisions",
    "Infrastructure Decisions",
    "Future Decisions",
]

# Map question types to DECISIONS.md sections.
TYPE_TO_SECTION = {
    "Business": "Business Decisions",
    "Product": "Product Decisions",
    "Architecture": "Technical Decisions",
    "Technical": "Technical Decisions",
    "Security": "Technical Decisions",
    "External Resource": "Infrastructure Decisions",
    "Infrastructure": "Infrastructure Decisions",
    "UI/UX": "UI/UX Decisions",
}


def read_decisions() -> str:
    """Return the full content of DECISIONS.md, or empty string if missing."""
    path = config.DECISIONS_MD
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def search_decisions(query: str) -> list[str]:
    """Search DECISIONS.md for entries matching the query (case-insensitive).

    Returns a list of matching decision blocks (## headings + content).
    """
    content = read_decisions()
    if not content:
        return []

    # Split into decision blocks by ## headings.
    blocks = re.split(r"(?=^## )", content, flags=re.MULTILINE)
    query_lower = query.lower()
    return [b.strip() for b in blocks if b.strip() and query_lower in b.lower()]


def has_existing_decision(question_text: str) -> Optional[str]:
    """Check if DECISIONS.md already contains a decision for this question.

    Returns the matching block text if found, None otherwise.
    """
    matches = search_decisions(question_text)
    if matches:
        logger.info("Found existing decision for: %s", question_text[:60])
        return matches[0]
    return None


def append_decision(
    title: str,
    decision_text: str,
    reasoning: str = "",
    source: str = "user (via Discord)",
    question_type: str = "",
) -> bool:
    """Append a new decision entry to the appropriate section of DECISIONS.md.

    Returns True on success.
    """
    path = config.DECISIONS_MD
    if not path.exists():
        logger.warning("DECISIONS.md not found at %s — creating it", path)
        _create_default(path)

    content = path.read_text(encoding="utf-8")
    section_name = TYPE_TO_SECTION.get(question_type, "Technical Decisions")

    entry = (
        f"\n## {title}\n"
        f"- **Decision:** {decision_text}\n"
        f"- **Date:** {date.today().isoformat()}\n"
        f"- **Reasoning:** {reasoning or 'Not provided'}\n"
        f"- **Source:** {source}\n"
    )

    # Find the section header and insert after the comment line or header.
    header = f"# {section_name}"
    idx = content.find(header)
    if idx == -1:
        # Section not found — append at end.
        content += f"\n{header}\n{entry}\n"
    else:
        # Find the end of the header line.
        line_end = content.index("\n", idx) + 1
        # Skip any HTML comment immediately after the header.
        rest = content[line_end:]
        comment_match = re.match(r"\s*<!--.*?-->\s*\n?", rest, re.DOTALL)
        if comment_match:
            insert_pos = line_end + comment_match.end()
        else:
            insert_pos = line_end
        content = content[:insert_pos] + entry + content[insert_pos:]

    path.write_text(content, encoding="utf-8")
    logger.info("Appended decision '%s' to section '%s'", title, section_name)
    return True


def _create_default(path: Path):
    """Create a default DECISIONS.md."""
    lines = []
    for section in SECTIONS:
        lines.append(f"# {section}\n")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
