"""Monitor agent context-window utilisation and fire threshold actions.

Thresholds:
  50% — checkpoint: save PROJECT_CONTEXT.md
  60% — prepare: generate SESSION_HANDOFF.md draft
  65% — wrap up: finalize handoff, stop new tasks
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from automation import config
from automation.providers.base import ContextProvider
from automation.storage.models import ContextLevel

logger = logging.getLogger("automation.agents.context_monitor")


@dataclass
class ThresholdState:
    """Tracks which thresholds have already fired for the current session."""
    session_id: str = ""
    checkpoint_fired: bool = False  # 50%
    handoff_fired: bool = False     # 60%
    wrapup_fired: bool = False      # 65%


class ContextMonitor:
    """Polls a ContextProvider and emits callbacks when thresholds are crossed."""

    def __init__(
        self,
        provider: ContextProvider,
        on_checkpoint: Optional[Callable[[ContextLevel], None]] = None,
        on_handoff: Optional[Callable[[ContextLevel], None]] = None,
        on_wrapup: Optional[Callable[[ContextLevel], None]] = None,
    ):
        self._provider = provider
        self._on_checkpoint = on_checkpoint
        self._on_handoff = on_handoff
        self._on_wrapup = on_wrapup
        self._state = ThresholdState()
        self._last_level: Optional[ContextLevel] = None

    @property
    def last_level(self) -> Optional[ContextLevel]:
        return self._last_level

    def reset(self, session_id: str = "") -> None:
        """Reset threshold state for a new session."""
        self._state = ThresholdState(session_id=session_id)
        self._last_level = None

    def check(self) -> Optional[ContextLevel]:
        """Read the current context level and fire any newly-crossed thresholds.

        Returns the current level, or None if unavailable.
        """
        level = self._provider.read_level()
        if level is None:
            return None

        self._last_level = level

        # Reset state if the session changed.
        if level.session_id and level.session_id != self._state.session_id:
            logger.info("New session detected: %s", level.session_id)
            self._state = ThresholdState(session_id=level.session_id)

        pct = level.pct

        # Check thresholds in ascending order.
        if pct >= config.CONTEXT_THRESHOLD_CHECKPOINT and not self._state.checkpoint_fired:
            self._state.checkpoint_fired = True
            logger.info("Context threshold: checkpoint (%d%% >= %d%%)", pct, config.CONTEXT_THRESHOLD_CHECKPOINT)
            if self._on_checkpoint:
                try:
                    self._on_checkpoint(level)
                except Exception:
                    logger.exception("Checkpoint callback failed")

        if pct >= config.CONTEXT_THRESHOLD_HANDOFF and not self._state.handoff_fired:
            self._state.handoff_fired = True
            logger.info("Context threshold: handoff (%d%% >= %d%%)", pct, config.CONTEXT_THRESHOLD_HANDOFF)
            if self._on_handoff:
                try:
                    self._on_handoff(level)
                except Exception:
                    logger.exception("Handoff callback failed")

        if pct >= config.CONTEXT_THRESHOLD_WRAPUP and not self._state.wrapup_fired:
            self._state.wrapup_fired = True
            logger.info("Context threshold: wrapup (%d%% >= %d%%)", pct, config.CONTEXT_THRESHOLD_WRAPUP)
            if self._on_wrapup:
                try:
                    self._on_wrapup(level)
                except Exception:
                    logger.exception("Wrapup callback failed")

        return level
