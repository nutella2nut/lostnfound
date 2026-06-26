"""Tests for automation.agents.handoff."""

import pytest

from automation.agents.handoff import (
    HandoffData,
    archive_handoff,
    parse_handoff,
    read_handoff,
    write_handoff,
)

SAMPLE_MD = """\
# Session Handoff
- **Session ID:** abc123
- **Created:** 2026-06-23T14:30:00Z
- **Context Used:** 62%

## Current Task
Implementing OAuth2 flow

## Completed This Session
- Email submission flow
- HEIC conversion

## Remaining Work
- Magic link auth
- S3 storage

## Open Questions
(none)

## Key Files Modified
- inventory/views.py
- inventory/models.py

## Decisions Made This Session
- Use XOAUTH2 for IMAP

## Resume Instructions
Test token refresh against live M365 first.
"""


def test_parse_handoff_extracts_all_fields():
    data = parse_handoff(SAMPLE_MD)

    assert data.session_id == "abc123"
    assert data.created == "2026-06-23T14:30:00Z"
    assert data.context_pct == 62
    assert data.current_task == "Implementing OAuth2 flow"
    assert data.completed_this_session == ["Email submission flow", "HEIC conversion"]
    assert data.remaining_work == ["Magic link auth", "S3 storage"]
    assert data.open_questions == []
    assert data.key_files_modified == ["inventory/views.py", "inventory/models.py"]
    assert data.decisions_this_session == ["Use XOAUTH2 for IMAP"]
    assert data.resume_instructions == "Test token refresh against live M365 first."
    assert data.raw_text == SAMPLE_MD


def test_write_handoff_creates_correct_markdown(tmp_path):
    data = HandoffData(
        session_id="abc123",
        created="2026-06-23T14:30:00Z",
        context_pct=62,
        current_task="Implementing OAuth2 flow",
        completed_this_session=["Email submission flow", "HEIC conversion"],
        remaining_work=["Magic link auth", "S3 storage"],
        open_questions=[],
        key_files_modified=["inventory/views.py", "inventory/models.py"],
        decisions_this_session=["Use XOAUTH2 for IMAP"],
        resume_instructions="Test token refresh against live M365 first.",
    )

    p = tmp_path / "HANDOFF.md"
    result_path = write_handoff(data, path=p)

    assert result_path == p
    content = p.read_text(encoding="utf-8")
    assert "**Session ID:** abc123" in content
    assert "**Context Used:** 62%" in content
    assert "Implementing OAuth2 flow" in content
    assert "- Email submission flow" in content
    assert "- HEIC conversion" in content
    assert "- Magic link auth" in content
    assert "(none)" in content  # open_questions is empty
    assert "- inventory/views.py" in content
    assert "- Use XOAUTH2 for IMAP" in content
    assert "Test token refresh against live M365 first." in content


def test_write_parse_round_trip(tmp_path):
    original = HandoffData(
        session_id="roundtrip-1",
        created="2026-06-23T15:00:00Z",
        context_pct=45,
        current_task="Build tests",
        completed_this_session=["Setup project"],
        remaining_work=["Deploy"],
        open_questions=["Which cloud?"],
        key_files_modified=["main.py"],
        decisions_this_session=["Use pytest"],
        resume_instructions="Run the test suite first.",
    )

    p = tmp_path / "HANDOFF.md"
    write_handoff(original, path=p)
    parsed = parse_handoff(p.read_text(encoding="utf-8"))

    assert parsed.session_id == original.session_id
    assert parsed.created == original.created
    assert parsed.context_pct == original.context_pct
    assert parsed.current_task == original.current_task
    assert parsed.completed_this_session == original.completed_this_session
    assert parsed.remaining_work == original.remaining_work
    assert parsed.open_questions == original.open_questions
    assert parsed.key_files_modified == original.key_files_modified
    assert parsed.decisions_this_session == original.decisions_this_session
    assert parsed.resume_instructions == original.resume_instructions


def test_read_handoff_returns_none_for_missing_file(tmp_path):
    p = tmp_path / "nonexistent.md"

    result = read_handoff(path=p)
    assert result is None


def test_archive_handoff_copies_file_with_timestamp(tmp_path, monkeypatch):
    import automation.agents.handoff as handoff_module

    # Create the handoff file.
    handoff_file = tmp_path / "HANDOFF.md"
    handoff_file.write_text(SAMPLE_MD, encoding="utf-8")

    # Point the archive dir to a temp location.
    archive_dir = tmp_path / "archive"
    monkeypatch.setattr(handoff_module.config, "HANDOFF_ARCHIVE_DIR", archive_dir)

    dest = archive_handoff(path=handoff_file)

    assert dest is not None
    assert dest.exists()
    assert dest.parent == archive_dir
    assert dest.name.startswith("SESSION_HANDOFF_")
    assert dest.name.endswith(".md")
    assert dest.read_text(encoding="utf-8") == SAMPLE_MD


def test_archive_handoff_returns_none_for_missing_file(tmp_path):
    p = tmp_path / "nonexistent.md"

    result = archive_handoff(path=p)
    assert result is None
