"""Tests for automation.agents.context_monitor."""

import pytest

from automation.agents.context_monitor import ContextMonitor
from automation.providers.base import ContextProvider
from automation.storage.models import ContextLevel


class MockContextProvider(ContextProvider):
    def __init__(self):
        self._level = None

    def read_level(self):
        return self._level

    def write_level(self, level):
        self._level = level


def test_check_returns_none_when_no_level():
    provider = MockContextProvider()
    monitor = ContextMonitor(provider)

    result = monitor.check()
    assert result is None


def test_check_returns_level_when_available():
    provider = MockContextProvider()
    provider._level = ContextLevel(pct=30, session_id="s1")
    monitor = ContextMonitor(provider)

    result = monitor.check()
    assert result is not None
    assert result.pct == 30
    assert result.session_id == "s1"


def test_checkpoint_callback_fires_at_50_only_once():
    provider = MockContextProvider()
    calls = []
    monitor = ContextMonitor(provider, on_checkpoint=lambda lvl: calls.append(lvl))

    provider._level = ContextLevel(pct=50, session_id="s1")
    monitor.check()
    assert len(calls) == 1
    assert calls[0].pct == 50

    # Second check at same level should not fire again.
    monitor.check()
    assert len(calls) == 1


def test_handoff_callback_fires_at_60_only_once():
    provider = MockContextProvider()
    calls = []
    monitor = ContextMonitor(provider, on_handoff=lambda lvl: calls.append(lvl))

    provider._level = ContextLevel(pct=60, session_id="s1")
    monitor.check()
    assert len(calls) == 1

    monitor.check()
    assert len(calls) == 1


def test_wrapup_callback_fires_at_65_only_once():
    provider = MockContextProvider()
    calls = []
    monitor = ContextMonitor(provider, on_wrapup=lambda lvl: calls.append(lvl))

    provider._level = ContextLevel(pct=65, session_id="s1")
    monitor.check()
    assert len(calls) == 1

    monitor.check()
    assert len(calls) == 1


def test_all_three_callbacks_fire_in_sequence():
    provider = MockContextProvider()
    checkpoint_calls = []
    handoff_calls = []
    wrapup_calls = []

    monitor = ContextMonitor(
        provider,
        on_checkpoint=lambda lvl: checkpoint_calls.append(lvl),
        on_handoff=lambda lvl: handoff_calls.append(lvl),
        on_wrapup=lambda lvl: wrapup_calls.append(lvl),
    )

    # A single check at 70% should trigger all three.
    provider._level = ContextLevel(pct=70, session_id="s1")
    monitor.check()

    assert len(checkpoint_calls) == 1
    assert len(handoff_calls) == 1
    assert len(wrapup_calls) == 1


def test_reset_clears_thresholds_callbacks_fire_again():
    provider = MockContextProvider()
    calls = []
    monitor = ContextMonitor(provider, on_checkpoint=lambda lvl: calls.append(lvl))

    provider._level = ContextLevel(pct=50, session_id="s1")
    monitor.check()
    assert len(calls) == 1

    monitor.reset(session_id="s2")

    provider._level = ContextLevel(pct=50, session_id="s2")
    monitor.check()
    assert len(calls) == 2


def test_session_change_resets_thresholds():
    provider = MockContextProvider()
    calls = []
    monitor = ContextMonitor(provider, on_checkpoint=lambda lvl: calls.append(lvl))

    provider._level = ContextLevel(pct=50, session_id="s1")
    monitor.check()
    assert len(calls) == 1

    # New session id triggers automatic reset.
    provider._level = ContextLevel(pct=50, session_id="s2")
    monitor.check()
    assert len(calls) == 2
