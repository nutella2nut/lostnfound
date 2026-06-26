"""Tests for automation.storage.database.Database."""

import pytest

from automation.storage.database import Database
from automation.storage.models import (
    AgentEvent,
    Answer,
    Instruction,
    InstructionStatus,
    Question,
    QuestionStatus,
)


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


# ── Questions ──


def test_insert_and_retrieve_question(db):
    q = Question(project_slug="proj", question="What color?", question_type="Product")
    q = db.insert_question(q)
    assert q.id is not None

    fetched = db.get_question(q.id)
    assert fetched is not None
    assert fetched.question == "What color?"
    assert fetched.project_slug == "proj"
    assert fetched.status == QuestionStatus.PENDING


def test_get_pending_questions_excludes_answered(db):
    q1 = db.insert_question(Question(project_slug="p", question="q1"))
    q2 = db.insert_question(Question(project_slug="p", question="q2"))
    db.update_question_status(q2.id, QuestionStatus.ANSWERED)

    pending = db.get_pending_questions()
    assert len(pending) == 1
    assert pending[0].id == q1.id


def test_update_question_status(db):
    q = db.insert_question(Question(project_slug="p", question="q"))
    db.update_question_status(q.id, QuestionStatus.SENT, discord_message_id=123, discord_channel_id=456)

    updated = db.get_question(q.id)
    assert updated.status == QuestionStatus.SENT
    assert updated.discord_message_id == 123
    assert updated.discord_channel_id == 456


def test_find_duplicate(db):
    db.insert_question(Question(project_slug="p", question="same question"))

    dup = db.find_duplicate("p", "same question")
    assert dup is not None
    assert dup.question == "same question"

    no_dup = db.find_duplicate("p", "different question")
    assert no_dup is None


# ── Events ──


def test_insert_and_retrieve_event(db):
    event = AgentEvent(type="milestone", session_id="s1", data={"step": 1})
    row_id = db.insert_event(event)
    assert row_id >= 1

    events = db.get_recent_events()
    assert len(events) == 1
    assert events[0].type == "milestone"
    assert events[0].session_id == "s1"
    assert events[0].data == {"step": 1}


def test_get_recent_events_respects_limit(db):
    for i in range(5):
        db.insert_event(AgentEvent(type="progress_update", session_id="s1", data={"i": i}))

    events = db.get_recent_events(limit=3)
    assert len(events) == 3


def test_get_recent_events_filters_by_type(db):
    db.insert_event(AgentEvent(type="milestone", session_id="s1"))
    db.insert_event(AgentEvent(type="error", session_id="s1"))
    db.insert_event(AgentEvent(type="milestone", session_id="s1"))

    milestones = db.get_recent_events(event_type="milestone")
    assert len(milestones) == 2
    assert all(e.type == "milestone" for e in milestones)


def test_get_recent_events_newest_first(db):
    db.insert_event(AgentEvent(type="progress_update", session_id="s1", timestamp="2025-01-01T00:00:00Z"))
    db.insert_event(AgentEvent(type="progress_update", session_id="s1", timestamp="2025-06-01T00:00:00Z"))
    db.insert_event(AgentEvent(type="progress_update", session_id="s1", timestamp="2025-03-01T00:00:00Z"))

    events = db.get_recent_events()
    timestamps = [e.timestamp for e in events]
    assert timestamps == sorted(timestamps, reverse=True)


# ── Instructions ──


def test_insert_and_retrieve_instruction(db):
    instr = Instruction(project_slug="proj", instruction_text="do the thing", discord_username="alice")
    instr = db.insert_instruction(instr)

    pending = db.get_pending_instructions()
    assert len(pending) == 1
    assert pending[0].id == instr.id
    assert pending[0].instruction_text == "do the thing"


def test_get_pending_instructions_filters_by_project(db):
    db.insert_instruction(Instruction(project_slug="alpha", instruction_text="a"))
    db.insert_instruction(Instruction(project_slug="beta", instruction_text="b"))

    alpha = db.get_pending_instructions(project_slug="alpha")
    assert len(alpha) == 1
    assert alpha[0].project_slug == "alpha"


def test_update_instruction_status_to_acknowledged(db):
    instr = db.insert_instruction(Instruction(project_slug="p", instruction_text="x"))
    db.update_instruction_status(instr.id, InstructionStatus.ACKNOWLEDGED)

    pending = db.get_pending_instructions()
    assert len(pending) == 0


def test_acknowledged_instructions_not_pending(db):
    i1 = db.insert_instruction(Instruction(project_slug="p", instruction_text="keep"))
    i2 = db.insert_instruction(Instruction(project_slug="p", instruction_text="ack me"))
    db.update_instruction_status(i2.id, InstructionStatus.ACKNOWLEDGED)

    pending = db.get_pending_instructions()
    assert len(pending) == 1
    assert pending[0].id == i1.id
