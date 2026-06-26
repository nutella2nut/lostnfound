"""Tests for file-based providers."""

import json

import pytest

from automation.providers.file import (
    FileContextProvider,
    FileEventProvider,
    FileInstructionProvider,
)
from automation.storage.models import (
    AgentEvent,
    ContextLevel,
    Instruction,
    InstructionStatus,
)


# ── FileContextProvider ──


def test_context_read_missing_file(tmp_path):
    provider = FileContextProvider(tmp_path)
    assert provider.read_level() is None


def test_context_write_read_round_trip(tmp_path):
    provider = FileContextProvider(tmp_path)
    level = ContextLevel(pct=42, session_id="sess-1", timestamp="2026-01-01T00:00:00+00:00")
    provider.write_level(level)
    result = provider.read_level()
    assert result is not None
    assert result.pct == 42
    assert result.session_id == "sess-1"
    assert result.timestamp == "2026-01-01T00:00:00+00:00"


def test_context_write_is_atomic(tmp_path):
    """After write_level, only the final file exists (no leftover .tmp)."""
    provider = FileContextProvider(tmp_path)
    provider.write_level(ContextLevel(pct=10))
    assert (tmp_path / "context_level.json").exists()
    assert not (tmp_path / "context_level.tmp").exists()


def test_context_read_malformed_json(tmp_path):
    path = tmp_path / "context_level.json"
    path.write_text("not valid json{{{", encoding="utf-8")
    provider = FileContextProvider(tmp_path)
    assert provider.read_level() is None


# ── FileEventProvider ──


def test_event_read_missing_file(tmp_path):
    provider = FileEventProvider(tmp_path)
    events, cursor = provider.read_new()
    assert events == []
    assert cursor == 0


def test_event_emit_and_read(tmp_path):
    provider = FileEventProvider(tmp_path)
    evt = AgentEvent(type="progress_update", session_id="s1", data={"step": 1})
    provider.emit(evt)
    events, cursor = provider.read_new()
    assert len(events) == 1
    assert events[0].type == "progress_update"
    assert events[0].data == {"step": 1}
    assert cursor == 1


def test_event_cursor_pagination(tmp_path):
    provider = FileEventProvider(tmp_path)
    for i in range(3):
        provider.emit(AgentEvent(type=f"evt_{i}", session_id="s1"))

    # Read first 2 (after_line=0 reads all, so we read all then simulate)
    events, cursor = provider.read_new(after_line=0)
    assert len(events) == 3
    assert cursor == 3

    # Read only events after line 2
    events, cursor = provider.read_new(after_line=2)
    assert len(events) == 1
    assert events[0].type == "evt_2"
    assert cursor == 3

    # Nothing new after cursor 3
    events, cursor = provider.read_new(after_line=3)
    assert events == []
    assert cursor == 3


def test_event_read_skips_malformed_lines(tmp_path):
    path = tmp_path / "events.jsonl"
    good = json.dumps({"type": "ok", "session_id": "s1", "data": {}, "timestamp": ""})
    path.write_text(f"bad json line\n{good}\n", encoding="utf-8")
    provider = FileEventProvider(tmp_path)
    events, cursor = provider.read_new()
    assert len(events) == 1
    assert events[0].type == "ok"
    assert cursor == 2  # total lines including the bad one


# ── FileInstructionProvider ──


def test_instruction_check_pending_empty(tmp_path):
    provider = FileInstructionProvider(tmp_path)
    assert provider.check_pending() == []


def test_instruction_submit_and_check_pending(tmp_path):
    provider = FileInstructionProvider(tmp_path)
    instr = Instruction(
        id="abc123",
        project_slug="proj",
        instruction_text="do the thing",
        discord_user_id="u1",
        discord_username="alice",
    )
    returned_id = provider.submit(instr)
    assert returned_id == "abc123"

    pending = provider.check_pending()
    assert len(pending) == 1
    assert pending[0].id == "abc123"
    assert pending[0].instruction_text == "do the thing"
    assert pending[0].status == InstructionStatus.PENDING


def test_instruction_lifecycle(tmp_path):
    """submit -> check_pending -> acknowledge -> check_pending returns empty."""
    provider = FileInstructionProvider(tmp_path)
    instr = Instruction(id="lifecycle1", instruction_text="fix bug")
    provider.submit(instr)

    pending = provider.check_pending()
    assert len(pending) == 1

    provider.acknowledge("lifecycle1")

    pending = provider.check_pending()
    assert len(pending) == 0

    # Ack file was created
    ack_path = tmp_path / "instruction_acks" / "ack_lifecycle1.json"
    assert ack_path.exists()
    ack_data = json.loads(ack_path.read_text(encoding="utf-8"))
    assert ack_data["instruction_id"] == "lifecycle1"


def test_instruction_check_pending_skips_malformed(tmp_path):
    instr_dir = tmp_path / "instructions"
    instr_dir.mkdir(parents=True)
    (instr_dir / "instr_bad.json").write_text("not json", encoding="utf-8")
    provider = FileInstructionProvider(tmp_path)
    assert provider.check_pending() == []


def test_pause_signal(tmp_path):
    provider = FileInstructionProvider(tmp_path)
    assert provider.is_paused() is False

    provider.write_pause()
    assert provider.is_paused() is True

    provider.clear_pause()
    assert provider.is_paused() is False


def test_clear_pause_when_not_paused(tmp_path):
    """clear_pause on a non-existent file should not raise."""
    provider = FileInstructionProvider(tmp_path)
    provider.clear_pause()  # no error
    assert provider.is_paused() is False
