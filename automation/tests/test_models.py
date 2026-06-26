"""Tests for storage models."""

import json

import pytest

from automation.storage.models import (
    AgentEvent,
    ContextLevel,
    Instruction,
    InstructionStatus,
    Question,
    QuestionStatus,
    SessionState,
)


# ── ContextLevel round-trip ──


def test_context_level_round_trip():
    cl = ContextLevel(pct=75, session_id="sess-42", timestamp="2026-06-01T12:00:00+00:00")
    d = cl.to_dict()
    restored = ContextLevel.from_dict(d)
    assert restored.pct == 75
    assert restored.session_id == "sess-42"
    assert restored.timestamp == "2026-06-01T12:00:00+00:00"


def test_context_level_from_dict_defaults():
    cl = ContextLevel.from_dict({})
    assert cl.pct == 0
    assert cl.session_id == ""
    assert cl.timestamp == ""


# ── AgentEvent round-trip ──


def test_agent_event_round_trip():
    evt = AgentEvent(type="milestone", session_id="s1", data={"msg": "done"}, timestamp="t1")
    d = evt.to_dict()
    restored = AgentEvent.from_dict(d)
    assert restored.type == "milestone"
    assert restored.session_id == "s1"
    assert restored.data == {"msg": "done"}
    assert restored.timestamp == "t1"


def test_agent_event_from_dict_defaults():
    evt = AgentEvent.from_dict({})
    assert evt.type == ""
    assert evt.data == {}


# ── Instruction round-trip ──


def test_instruction_round_trip():
    instr = Instruction(
        id="id123",
        project_slug="proj",
        instruction_text="deploy",
        discord_user_id="u1",
        discord_username="bob",
        status=InstructionStatus.ACKNOWLEDGED,
        created_at="2026-01-01T00:00:00+00:00",
        acknowledged_at="2026-01-01T00:01:00+00:00",
    )
    d = instr.to_dict()
    restored = Instruction.from_dict(d)
    assert restored.id == "id123"
    assert restored.instruction_text == "deploy"
    assert restored.status == InstructionStatus.ACKNOWLEDGED
    assert restored.acknowledged_at == "2026-01-01T00:01:00+00:00"


def test_instruction_to_dict_serializes_status_as_string():
    instr = Instruction(status=InstructionStatus.PENDING)
    d = instr.to_dict()
    assert d["status"] == "pending"
    assert isinstance(d["status"], str)


# ── Question.options_list ──


def test_question_options_list_valid_json():
    opts = json.dumps([{"label": "A", "text": "Option A"}, {"label": "B", "text": "Option B"}])
    q = Question(options=opts)
    result = q.options_list()
    assert len(result) == 2
    assert result[0]["label"] == "A"


def test_question_options_list_empty_string():
    q = Question(options="")
    assert q.options_list() == []


def test_question_options_list_invalid_json():
    q = Question(options="not json at all")
    assert q.options_list() == []


# ── Enum values are strings ──


@pytest.mark.parametrize(
    "enum_cls",
    [QuestionStatus, InstructionStatus, SessionState],
)
def test_enum_values_are_strings(enum_cls):
    for member in enum_cls:
        assert isinstance(member.value, str), f"{enum_cls.__name__}.{member.name} value is not a string"
