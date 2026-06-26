"""Read, write, and archive SESSION_HANDOFF.md."""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from automation import config

logger = logging.getLogger("automation.agents.handoff")


@dataclass
class HandoffData:
    """Parsed representation of SESSION_HANDOFF.md."""
    session_id: str = ""
    created: str = ""
    context_pct: int = 0
    current_task: str = ""
    completed_this_session: list[str] = field(default_factory=list)
    remaining_work: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    key_files_modified: list[str] = field(default_factory=list)
    decisions_this_session: list[str] = field(default_factory=list)
    resume_instructions: str = ""
    raw_text: str = ""


def read_handoff(path: Optional[Path] = None) -> Optional[HandoffData]:
    """Read and parse SESSION_HANDOFF.md. Returns None if missing."""
    path = path or config.SESSION_HANDOFF_MD
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    return parse_handoff(text)


def parse_handoff(text: str) -> HandoffData:
    """Parse SESSION_HANDOFF.md content."""
    data = HandoffData(raw_text=text)

    # Extract metadata from bullet list at top.
    for m in re.finditer(r"\*\*Session ID:\*\*\s*(.+)", text):
        data.session_id = m.group(1).strip()
    for m in re.finditer(r"\*\*Created:\*\*\s*(.+)", text):
        data.created = m.group(1).strip()
    for m in re.finditer(r"\*\*Context Used:\*\*\s*(\d+)", text):
        data.context_pct = int(m.group(1))

    section_map = {
        "current task": "current_task",
        "completed this session": "completed_this_session",
        "remaining work": "remaining_work",
        "open questions": "open_questions",
        "key files modified": "key_files_modified",
        "decisions made this session": "decisions_this_session",
        "resume instructions": "resume_instructions",
    }

    sections = re.split(r"^##\s+", text, flags=re.MULTILINE)
    for section in sections:
        if not section.strip():
            continue
        lines = section.split("\n", 1)
        heading = lines[0].strip().lower()
        content = lines[1].strip() if len(lines) > 1 else ""

        for key, attr in section_map.items():
            if key in heading:
                if attr in ("current_task", "resume_instructions"):
                    setattr(data, attr, content)
                else:
                    setattr(data, attr, _extract_items(content))
                break

    return data


def write_handoff(data: HandoffData, path: Optional[Path] = None) -> Path:
    """Write SESSION_HANDOFF.md from structured data."""
    path = path or config.SESSION_HANDOFF_MD

    def _bullet_list(items: list[str]) -> str:
        if not items:
            return "(none)\n"
        return "\n".join(f"- {item}" for item in items) + "\n"

    content = (
        f"# Session Handoff\n"
        f"- **Session ID:** {data.session_id}\n"
        f"- **Created:** {data.created}\n"
        f"- **Context Used:** {data.context_pct}%\n"
        f"\n"
        f"## Current Task\n"
        f"{data.current_task or '(none)'}\n"
        f"\n"
        f"## Completed This Session\n"
        f"{_bullet_list(data.completed_this_session)}"
        f"\n"
        f"## Remaining Work\n"
        f"{_bullet_list(data.remaining_work)}"
        f"\n"
        f"## Open Questions\n"
        f"{_bullet_list(data.open_questions)}"
        f"\n"
        f"## Key Files Modified\n"
        f"{_bullet_list(data.key_files_modified)}"
        f"\n"
        f"## Decisions Made This Session\n"
        f"{_bullet_list(data.decisions_this_session)}"
        f"\n"
        f"## Resume Instructions\n"
        f"{data.resume_instructions or '(none)'}\n"
    )

    path.write_text(content, encoding="utf-8")
    logger.info("SESSION_HANDOFF.md written: session=%s", data.session_id)
    return path


def archive_handoff(path: Optional[Path] = None) -> Optional[Path]:
    """Archive the current SESSION_HANDOFF.md with a timestamp suffix."""
    path = path or config.SESSION_HANDOFF_MD
    if not path.exists():
        return None

    archive_dir = config.HANDOFF_ARCHIVE_DIR
    archive_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = archive_dir / f"SESSION_HANDOFF_{ts}.md"
    shutil.copy2(str(path), str(dest))
    logger.info("Archived handoff to %s", dest)
    return dest


def _extract_items(text: str) -> list[str]:
    """Extract bullet-list items from markdown text."""
    items = []
    for line in text.split("\n"):
        line = line.strip()
        m = re.match(r"^[-*]\s+(.+)$", line)
        if m:
            items.append(m.group(1).strip())
            continue
        m = re.match(r"^\d+\.\s+(.+)$", line)
        if m:
            items.append(m.group(1).strip())
    return items
