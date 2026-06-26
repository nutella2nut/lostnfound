"""SQLite persistence layer. Survives bot/machine/process restarts."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from automation.storage.models import (
    AgentEvent,
    Answer,
    Instruction,
    InstructionStatus,
    Question,
    QuestionStatus,
)

logger = logging.getLogger("automation.storage")

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS questions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_slug    TEXT NOT NULL,
    question_type   TEXT NOT NULL DEFAULT '',
    question        TEXT NOT NULL,
    context         TEXT NOT NULL DEFAULT '',
    options         TEXT NOT NULL DEFAULT '[]',
    recommended     TEXT NOT NULL DEFAULT '',
    rationale       TEXT NOT NULL DEFAULT '',
    expected_impact TEXT NOT NULL DEFAULT '',
    confidence      TEXT NOT NULL DEFAULT '',
    raw_block       TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending',
    discord_message_id  INTEGER,
    discord_channel_id  INTEGER,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS answers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id     INTEGER NOT NULL REFERENCES questions(id),
    answer_text     TEXT NOT NULL,
    answer_option   TEXT NOT NULL DEFAULT '',
    discord_user_id TEXT NOT NULL DEFAULT '',
    discord_username TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    data_json       TEXT NOT NULL DEFAULT '{}',
    discord_message_id INTEGER,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS instructions (
    id              TEXT PRIMARY KEY,
    project_slug    TEXT NOT NULL,
    instruction_text TEXT NOT NULL,
    discord_user_id TEXT NOT NULL DEFAULT '',
    discord_username TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT NOT NULL,
    acknowledged_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(status);
CREATE INDEX IF NOT EXISTS idx_questions_project ON questions(project_slug);
CREATE INDEX IF NOT EXISTS idx_answers_question ON answers(question_id);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_instructions_status ON instructions(status);
CREATE INDEX IF NOT EXISTS idx_instructions_project ON instructions(project_slug);
"""


class Database:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(_CREATE_TABLES)
        logger.info("Database initialized at %s", self._db_path)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Questions ──

    def insert_question(self, q: Question) -> Question:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO questions
                   (project_slug, question_type, question, context, options,
                    recommended, rationale, expected_impact, confidence,
                    raw_block, status, discord_message_id, discord_channel_id,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    q.project_slug, q.question_type, q.question, q.context,
                    q.options, q.recommended, q.rationale, q.expected_impact,
                    q.confidence, q.raw_block, q.status.value,
                    q.discord_message_id, q.discord_channel_id,
                    q.created_at, q.updated_at,
                ),
            )
            q.id = cur.lastrowid
        logger.info("Inserted question id=%d slug=%s", q.id, q.project_slug)
        return q

    def get_question(self, question_id: int) -> Optional[Question]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM questions WHERE id = ?", (question_id,)
            ).fetchone()
        return self._row_to_question(row) if row else None

    def get_pending_questions(self, project_slug: str = "") -> list[Question]:
        with self._connect() as conn:
            if project_slug:
                rows = conn.execute(
                    "SELECT * FROM questions WHERE status = 'pending' AND project_slug = ? ORDER BY created_at",
                    (project_slug,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM questions WHERE status = 'pending' ORDER BY created_at"
                ).fetchall()
        return [self._row_to_question(r) for r in rows]

    def get_sent_questions(self, project_slug: str = "") -> list[Question]:
        with self._connect() as conn:
            if project_slug:
                rows = conn.execute(
                    "SELECT * FROM questions WHERE status = 'sent' AND project_slug = ? ORDER BY created_at",
                    (project_slug,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM questions WHERE status = 'sent' ORDER BY created_at"
                ).fetchall()
        return [self._row_to_question(r) for r in rows]

    def update_question_status(
        self, question_id: int, status: QuestionStatus,
        discord_message_id: Optional[int] = None,
        discord_channel_id: Optional[int] = None,
    ):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            if discord_message_id is not None:
                conn.execute(
                    """UPDATE questions
                       SET status = ?, discord_message_id = ?, discord_channel_id = ?, updated_at = ?
                       WHERE id = ?""",
                    (status.value, discord_message_id, discord_channel_id, now, question_id),
                )
            else:
                conn.execute(
                    "UPDATE questions SET status = ?, updated_at = ? WHERE id = ?",
                    (status.value, now, question_id),
                )
        logger.info("Question id=%d status -> %s", question_id, status.value)

    def find_duplicate(self, project_slug: str, question_text: str) -> Optional[Question]:
        """Check if the same question is already pending or sent."""
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM questions
                   WHERE project_slug = ? AND question = ? AND status IN ('pending', 'sent')
                   LIMIT 1""",
                (project_slug, question_text),
            ).fetchone()
        return self._row_to_question(row) if row else None

    # ── Answers ──

    def insert_answer(self, a: Answer) -> Answer:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO answers
                   (question_id, answer_text, answer_option, discord_user_id, discord_username, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (a.question_id, a.answer_text, a.answer_option,
                 a.discord_user_id, a.discord_username, a.created_at),
            )
            a.id = cur.lastrowid
        logger.info("Inserted answer id=%d for question_id=%d", a.id, a.question_id)
        return a

    def get_answer_for_question(self, question_id: int) -> Optional[Answer]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM answers WHERE question_id = ? ORDER BY created_at DESC LIMIT 1",
                (question_id,),
            ).fetchone()
        return self._row_to_answer(row) if row else None

    # ── Events ──

    def insert_event(self, event: AgentEvent) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO events (session_id, event_type, data_json, discord_message_id, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (event.session_id, event.type, json.dumps(event.data),
                 event.discord_message_id, event.timestamp),
            )
            row_id = cur.lastrowid
        logger.info("Inserted event id=%d type=%s", row_id, event.type)
        return row_id

    def get_recent_events(self, limit: int = 20, event_type: str = "") -> list[AgentEvent]:
        with self._connect() as conn:
            if event_type:
                rows = conn.execute(
                    "SELECT * FROM events WHERE event_type = ? ORDER BY created_at DESC LIMIT ?",
                    (event_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM events ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_event(r) for r in rows]

    # ── Instructions ──

    def insert_instruction(self, instr: Instruction) -> Instruction:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO instructions
                   (id, project_slug, instruction_text, discord_user_id, discord_username,
                    status, created_at, acknowledged_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (instr.id, instr.project_slug, instr.instruction_text,
                 instr.discord_user_id, instr.discord_username,
                 instr.status.value, instr.created_at, instr.acknowledged_at),
            )
        logger.info("Inserted instruction id=%s", instr.id)
        return instr

    def get_pending_instructions(self, project_slug: str = "") -> list[Instruction]:
        with self._connect() as conn:
            if project_slug:
                rows = conn.execute(
                    "SELECT * FROM instructions WHERE status = 'pending' AND project_slug = ? ORDER BY created_at",
                    (project_slug,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM instructions WHERE status = 'pending' ORDER BY created_at"
                ).fetchall()
        return [self._row_to_instruction(r) for r in rows]

    def update_instruction_status(self, instruction_id: str, status: InstructionStatus) -> None:
        from automation.storage.models import _now_iso
        with self._connect() as conn:
            ack_at = _now_iso() if status == InstructionStatus.ACKNOWLEDGED else None
            conn.execute(
                "UPDATE instructions SET status = ?, acknowledged_at = COALESCE(?, acknowledged_at) WHERE id = ?",
                (status.value, ack_at, instruction_id),
            )
        logger.info("Instruction id=%s status -> %s", instruction_id, status.value)

    # ── Helpers ──

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> AgentEvent:
        return AgentEvent(
            type=row["event_type"],
            session_id=row["session_id"],
            data=json.loads(row["data_json"]) if row["data_json"] else {},
            timestamp=row["created_at"],
            discord_message_id=row["discord_message_id"],
        )

    @staticmethod
    def _row_to_instruction(row: sqlite3.Row) -> Instruction:
        return Instruction(
            id=row["id"],
            project_slug=row["project_slug"],
            instruction_text=row["instruction_text"],
            discord_user_id=row["discord_user_id"],
            discord_username=row["discord_username"],
            status=InstructionStatus(row["status"]),
            created_at=row["created_at"],
            acknowledged_at=row["acknowledged_at"],
        )

    @staticmethod
    def _row_to_question(row: sqlite3.Row) -> Question:
        return Question(
            id=row["id"],
            project_slug=row["project_slug"],
            question_type=row["question_type"],
            question=row["question"],
            context=row["context"],
            options=row["options"],
            recommended=row["recommended"],
            rationale=row["rationale"],
            expected_impact=row["expected_impact"],
            confidence=row["confidence"],
            raw_block=row["raw_block"],
            status=QuestionStatus(row["status"]),
            discord_message_id=row["discord_message_id"],
            discord_channel_id=row["discord_channel_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_answer(row: sqlite3.Row) -> Answer:
        return Answer(
            id=row["id"],
            question_id=row["question_id"],
            answer_text=row["answer_text"],
            answer_option=row["answer_option"],
            discord_user_id=row["discord_user_id"],
            discord_username=row["discord_username"],
            created_at=row["created_at"],
        )
