"""File-based provider implementations (v1).

Communication between agent and bot happens through files in the state/ directory:
  - context_level.json   — agent writes, bot reads
  - events.jsonl          — agent appends, bot tails
  - instructions/*.json   — bot writes, agent reads
  - pause_signal          — bot writes/removes, agent reads
  - instruction_acks/*.json — agent writes, bot reads
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from automation.providers.base import ContextProvider, EventProvider, InstructionProvider
from automation.storage.models import AgentEvent, ContextLevel, Instruction, InstructionStatus

logger = logging.getLogger("automation.providers.file")


class FileContextProvider(ContextProvider):
    """Reads/writes context level via a JSON file."""

    def __init__(self, state_dir: Path):
        self._path = state_dir / "context_level.json"

    def read_level(self) -> Optional[ContextLevel]:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return ContextLevel.from_dict(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read context level: %s", exc)
            return None

    def write_level(self, level: ContextLevel) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(level.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(self._path)
        logger.debug("Context level written: %d%%", level.pct)


class FileEventProvider(EventProvider):
    """Appends/reads events via a JSONL file (one JSON object per line)."""

    def __init__(self, state_dir: Path):
        self._path = state_dir / "events.jsonl"

    def emit(self, event: AgentEvent) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event.to_dict(), separators=(",", ":")) + "\n"
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line)
        logger.debug("Event emitted: %s", event.type)

    def read_new(self, after_line: int = 0) -> tuple[list[AgentEvent], int]:
        if not self._path.exists():
            return [], 0
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError as exc:
            logger.warning("Failed to read events: %s", exc)
            return [], after_line

        new_events: list[AgentEvent] = []
        for line in lines[after_line:]:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                new_events.append(AgentEvent.from_dict(data))
            except json.JSONDecodeError:
                logger.warning("Skipping malformed event line: %s", line[:80])

        return new_events, len(lines)


class FileInstructionProvider(InstructionProvider):
    """Manages instructions via JSON files in a directory."""

    def __init__(self, state_dir: Path):
        self._instr_dir = state_dir / "instructions"
        self._ack_dir = state_dir / "instruction_acks"
        self._pause_path = state_dir / "pause_signal"

    def submit(self, instruction: Instruction) -> str:
        self._instr_dir.mkdir(parents=True, exist_ok=True)
        path = self._instr_dir / f"instr_{instruction.id}.json"
        path.write_text(json.dumps(instruction.to_dict(), indent=2), encoding="utf-8")
        logger.info("Instruction submitted: %s", instruction.id)
        return instruction.id

    def check_pending(self) -> list[Instruction]:
        if not self._instr_dir.exists():
            return []
        pending: list[Instruction] = []
        for path in sorted(self._instr_dir.glob("instr_*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                instr = Instruction.from_dict(data)
                if instr.status == InstructionStatus.PENDING:
                    pending.append(instr)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read instruction %s: %s", path.name, exc)
        return pending

    def acknowledge(self, instruction_id: str) -> None:
        from automation.storage.models import _now_iso
        # Update the instruction file status.
        instr_path = self._instr_dir / f"instr_{instruction_id}.json"
        if instr_path.exists():
            try:
                data = json.loads(instr_path.read_text(encoding="utf-8"))
                data["status"] = InstructionStatus.ACKNOWLEDGED.value
                data["acknowledged_at"] = _now_iso()
                instr_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to acknowledge instruction %s: %s", instruction_id, exc)

        # Write an ack file for the bot to detect.
        self._ack_dir.mkdir(parents=True, exist_ok=True)
        ack_path = self._ack_dir / f"ack_{instruction_id}.json"
        ack_path.write_text(
            json.dumps({"instruction_id": instruction_id, "acknowledged_at": _now_iso()}),
            encoding="utf-8",
        )
        logger.info("Instruction acknowledged: %s", instruction_id)

    def write_pause(self) -> None:
        self._pause_path.parent.mkdir(parents=True, exist_ok=True)
        self._pause_path.write_text("paused", encoding="utf-8")
        logger.info("Pause signal written")

    def clear_pause(self) -> None:
        if self._pause_path.exists():
            self._pause_path.unlink()
            logger.info("Pause signal cleared")

    def is_paused(self) -> bool:
        return self._pause_path.exists()
