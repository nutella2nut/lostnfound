"""Parse PROJECT_PROGRESS.md into structured sections."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from automation import config

logger = logging.getLogger("automation.agents.progress")


@dataclass
class ProgressReport:
    """Parsed representation of PROJECT_PROGRESS.md."""
    completed: list[str] = field(default_factory=list)
    in_progress: list[str] = field(default_factory=list)
    remaining: list[str] = field(default_factory=list)
    known_issues: list[str] = field(default_factory=list)
    technical_debt: list[str] = field(default_factory=list)
    recent_decisions: list[str] = field(default_factory=list)
    raw_text: str = ""


def read_progress(path: Optional[Path] = None) -> Optional[ProgressReport]:
    """Read and parse PROJECT_PROGRESS.md.

    Returns None if the file does not exist.
    """
    path = path or config.PROJECT_PROGRESS_MD
    if not path.exists():
        logger.info("PROJECT_PROGRESS.md not found at %s", path)
        return None

    text = path.read_text(encoding="utf-8")
    return parse_progress(text)


def parse_progress(text: str) -> ProgressReport:
    """Parse the content of PROJECT_PROGRESS.md into a ProgressReport."""
    report = ProgressReport(raw_text=text)

    # Map section header patterns to report fields.
    section_map = {
        "completed": "completed",
        "in progress": "in_progress",
        "remaining": "remaining",
        "known issues": "known_issues",
        "technical debt": "technical_debt",
        "recent decisions": "recent_decisions",
    }

    # Split content into sections by # headings.
    sections = re.split(r"^#+\s+", text, flags=re.MULTILINE)

    for section in sections:
        if not section.strip():
            continue
        # First line is the heading text, rest is content.
        lines = section.split("\n", 1)
        heading = lines[0].strip().lower()
        content = lines[1] if len(lines) > 1 else ""

        # Match heading to a known section.
        for key, attr in section_map.items():
            if key in heading:
                items = _extract_list_items(content)
                setattr(report, attr, items)
                break

    return report


def _extract_list_items(text: str) -> list[str]:
    """Extract markdown list items (- or * or numbered) from text."""
    items = []
    for line in text.split("\n"):
        line = line.strip()
        # Match "- [x] item", "- [ ] item", "- item", "* item", "1. item"
        m = re.match(r"^[-*]\s+(\[[ xX]\]\s+)?(.+)$", line)
        if m:
            items.append(m.group(2).strip())
            continue
        m = re.match(r"^\d+\.\s+(.+)$", line)
        if m:
            items.append(m.group(1).strip())
    return items


def get_current_task(path: Optional[Path] = None) -> Optional[str]:
    """Return the first in-progress item, or None."""
    report = read_progress(path)
    if report and report.in_progress:
        return report.in_progress[0]
    return None


def get_summary(path: Optional[Path] = None) -> dict:
    """Return a summary dict with counts per section."""
    report = read_progress(path)
    if not report:
        return {"exists": False}
    return {
        "exists": True,
        "completed_count": len(report.completed),
        "in_progress_count": len(report.in_progress),
        "remaining_count": len(report.remaining),
        "known_issues_count": len(report.known_issues),
        "technical_debt_count": len(report.technical_debt),
        "recent_decisions_count": len(report.recent_decisions),
    }
