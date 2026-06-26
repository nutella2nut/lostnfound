"""Tests for automation.agents.progress."""

import pytest

from automation.agents.progress import (
    ProgressReport,
    get_current_task,
    get_summary,
    parse_progress,
    read_progress,
)

SAMPLE_MD = """\
# Completed
- [x] Email submission flow
- [x] HEIC conversion

# In Progress
- [ ] OAuth2 integration

# Remaining
- [ ] Magic link auth
- [ ] S3 storage

# Known Issues
- Token refresh untested

# Technical Debt
- Legacy Bootstrap base template

# Recent Decisions
- Use XOAUTH2 for IMAP
"""


def test_parse_progress_extracts_all_sections():
    report = parse_progress(SAMPLE_MD)

    assert report.completed == ["Email submission flow", "HEIC conversion"]
    assert report.in_progress == ["OAuth2 integration"]
    assert report.remaining == ["Magic link auth", "S3 storage"]
    assert report.known_issues == ["Token refresh untested"]
    assert report.technical_debt == ["Legacy Bootstrap base template"]
    assert report.recent_decisions == ["Use XOAUTH2 for IMAP"]
    assert report.raw_text == SAMPLE_MD


def test_parse_progress_empty_text():
    report = parse_progress("")

    assert report.completed == []
    assert report.in_progress == []
    assert report.remaining == []
    assert report.known_issues == []
    assert report.technical_debt == []
    assert report.recent_decisions == []
    assert report.raw_text == ""


def test_parse_progress_no_sections():
    text = "Just some random text\nwith no markdown headings."
    report = parse_progress(text)

    assert report.completed == []
    assert report.in_progress == []
    assert report.remaining == []


def test_get_current_task_returns_first_in_progress(tmp_path):
    p = tmp_path / "PROGRESS.md"
    p.write_text(SAMPLE_MD, encoding="utf-8")

    result = get_current_task(path=p)
    assert result == "OAuth2 integration"


def test_get_current_task_returns_none_when_empty(tmp_path):
    p = tmp_path / "PROGRESS.md"
    p.write_text("# Completed\n- [x] Done\n", encoding="utf-8")

    result = get_current_task(path=p)
    assert result is None


def test_get_summary_returns_correct_counts(tmp_path):
    p = tmp_path / "PROGRESS.md"
    p.write_text(SAMPLE_MD, encoding="utf-8")

    summary = get_summary(path=p)
    assert summary["exists"] is True
    assert summary["completed_count"] == 2
    assert summary["in_progress_count"] == 1
    assert summary["remaining_count"] == 2
    assert summary["known_issues_count"] == 1
    assert summary["technical_debt_count"] == 1
    assert summary["recent_decisions_count"] == 1


def test_get_summary_missing_file(tmp_path):
    p = tmp_path / "nonexistent.md"

    summary = get_summary(path=p)
    assert summary == {"exists": False}


def test_read_progress_returns_none_for_missing_file(tmp_path):
    p = tmp_path / "nonexistent.md"

    result = read_progress(path=p)
    assert result is None


def test_read_progress_reads_and_parses(tmp_path):
    p = tmp_path / "PROGRESS.md"
    p.write_text(SAMPLE_MD, encoding="utf-8")

    result = read_progress(path=p)
    assert result is not None
    assert isinstance(result, ProgressReport)
    assert result.completed == ["Email submission flow", "HEIC conversion"]
    assert result.in_progress == ["OAuth2 integration"]
