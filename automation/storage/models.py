"""Data models for questions, answers, events, context, and instructions."""

from __future__ import annotations

import enum
import json as _json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Enums ──


class QuestionStatus(enum.Enum):
    PENDING = "pending"
    SENT = "sent"  # Delivered to Discord
    ANSWERED = "answered"
    EXPIRED = "expired"
    ERROR = "error"


class InstructionStatus(enum.Enum):
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    APPLIED = "applied"


class SessionState(enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    PAUSED = "paused"
    WRAPPING_UP = "wrapping_up"
    COMPLETED = "completed"
    FAILED = "failed"


# ── Existing models ──


@dataclass
class Question:
    id: Optional[int] = None
    project_slug: str = ""
    question_type: str = ""  # Business / Product / Architecture / Security / External Resource
    question: str = ""
    context: str = ""
    options: str = ""  # JSON-encoded list of {"label": "A", "text": "..."}
    recommended: str = ""
    rationale: str = ""
    expected_impact: str = ""
    confidence: str = ""
    raw_block: str = ""  # The full original text block
    status: QuestionStatus = QuestionStatus.PENDING
    discord_message_id: Optional[int] = None
    discord_channel_id: Optional[int] = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def options_list(self) -> list[dict]:
        """Return options as a list of dicts."""
        if not self.options:
            return []
        try:
            return _json.loads(self.options)
        except (_json.JSONDecodeError, TypeError):
            return []


@dataclass
class Answer:
    id: Optional[int] = None
    question_id: int = 0
    answer_text: str = ""
    answer_option: str = ""  # e.g. "A", "B", "C" or empty for freeform
    discord_user_id: str = ""
    discord_username: str = ""
    created_at: str = field(default_factory=_now_iso)


# ── New models ──


@dataclass
class ContextLevel:
    """Snapshot of the agent's context-window utilisation."""
    pct: int = 0
    session_id: str = ""
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {"pct": self.pct, "session_id": self.session_id, "timestamp": self.timestamp}

    @classmethod
    def from_dict(cls, d: dict) -> ContextLevel:
        return cls(pct=d.get("pct", 0), session_id=d.get("session_id", ""), timestamp=d.get("timestamp", ""))


@dataclass
class AgentEvent:
    """A lifecycle event emitted by the agent."""
    type: str = ""  # progress_update, context_checkpoint, session_start, session_end, error, milestone
    session_id: str = ""
    data: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=_now_iso)
    discord_message_id: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "session_id": self.session_id,
            "data": self.data,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> AgentEvent:
        return cls(
            type=d.get("type", ""),
            session_id=d.get("session_id", ""),
            data=d.get("data", {}),
            timestamp=d.get("timestamp", ""),
        )


@dataclass
class Instruction:
    """A human instruction sent to the agent via Discord."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    project_slug: str = ""
    instruction_text: str = ""
    discord_user_id: str = ""
    discord_username: str = ""
    status: InstructionStatus = InstructionStatus.PENDING
    created_at: str = field(default_factory=_now_iso)
    acknowledged_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_slug": self.project_slug,
            "instruction_text": self.instruction_text,
            "discord_user_id": self.discord_user_id,
            "discord_username": self.discord_username,
            "status": self.status.value,
            "created_at": self.created_at,
            "acknowledged_at": self.acknowledged_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Instruction:
        return cls(
            id=d.get("id", ""),
            project_slug=d.get("project_slug", ""),
            instruction_text=d.get("instruction_text", ""),
            discord_user_id=d.get("discord_user_id", ""),
            discord_username=d.get("discord_username", ""),
            status=InstructionStatus(d.get("status", "pending")),
            created_at=d.get("created_at", ""),
            acknowledged_at=d.get("acknowledged_at"),
        )
