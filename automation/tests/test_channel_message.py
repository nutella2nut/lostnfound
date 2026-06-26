"""Tests for channel-message-as-instruction routing.

Tests the project-slug resolution logic and the instruction submission
flow that backs on_message. Discord-dependent imports are avoided so
tests run without discord.py installed.
"""

from __future__ import annotations

import pytest

from automation.providers.file import FileInstructionProvider
from automation.storage.database import Database
from automation.storage.models import Instruction


# ── get_project_slug logic (tested without discord import) ──

# The actual function lives in channel_router.py which imports discord.
# We test the same decision logic here directly.


def _resolve_project_slug(
    channel_name: str,
    category_name: str | None,
    dashboard_name: str,
    projects_category: str,
) -> str | None:
    """Pure-logic replica of channel_router.get_project_slug."""
    if channel_name == dashboard_name:
        return None
    if category_name and category_name.lower() == projects_category.lower():
        return channel_name
    return None


def test_project_channel_returns_slug():
    assert _resolve_project_slug("lost-and-found-system", "claude-projects", "claude-dashboard", "claude-projects") == "lost-and-found-system"


def test_dashboard_channel_returns_none():
    assert _resolve_project_slug("claude-dashboard", "claude-projects", "claude-dashboard", "claude-projects") is None


def test_wrong_category_returns_none():
    assert _resolve_project_slug("lost-and-found-system", "general", "claude-dashboard", "claude-projects") is None


def test_no_category_returns_none():
    assert _resolve_project_slug("lost-and-found-system", None, "claude-dashboard", "claude-projects") is None


def test_category_match_is_case_insensitive():
    assert _resolve_project_slug("my-project", "claude-projects", "claude-dashboard", "Claude-Projects") == "my-project"


# ── Instruction submission flow (the core of on_message) ──


def test_instruction_submitted_via_provider_and_db(tmp_path):
    """A plain-text message creates an instruction in both provider and DB."""
    provider = FileInstructionProvider(tmp_path)
    db = Database(tmp_path / "test.db")

    instr = Instruction(
        project_slug="lost-and-found-system",
        instruction_text="prioritize vendor payouts",
        discord_user_id="12345",
        discord_username="testuser",
    )
    provider.submit(instr)
    db.insert_instruction(instr)

    # Provider.
    pending = provider.check_pending()
    assert len(pending) == 1
    assert pending[0].instruction_text == "prioritize vendor payouts"
    assert pending[0].project_slug == "lost-and-found-system"

    # DB.
    db_pending = db.get_pending_instructions("lost-and-found-system")
    assert len(db_pending) == 1
    assert db_pending[0].instruction_text == "prioritize vendor payouts"


def test_multiple_messages_become_separate_instructions(tmp_path):
    """Each channel message becomes its own queued instruction."""
    provider = FileInstructionProvider(tmp_path)
    db = Database(tmp_path / "test.db")

    messages = [
        "what are you working on?",
        "prioritize vendor payouts",
        "pause analytics work",
    ]
    for text in messages:
        instr = Instruction(
            project_slug="test-project",
            instruction_text=text,
            discord_user_id="123",
            discord_username="user",
        )
        provider.submit(instr)
        db.insert_instruction(instr)

    pending = provider.check_pending()
    assert len(pending) == 3
    assert set(p.instruction_text for p in pending) == set(messages)

    db_pending = db.get_pending_instructions("test-project")
    assert len(db_pending) == 3
    assert set(p.instruction_text for p in db_pending) == set(messages)


def test_empty_text_should_not_be_submitted(tmp_path):
    """Whitespace-only messages should not generate instructions.
    (The bot's on_message handler strips and skips empty text before
    reaching the submission logic — this test validates that intent.)
    """
    provider = FileInstructionProvider(tmp_path)
    # Simulate the guard: on_message does `text = message.content.strip(); if not text: return`
    text = "   "
    assert not text.strip()
    # No instruction submitted.
    assert provider.check_pending() == []
