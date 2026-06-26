"""Abstract provider interfaces for agent ↔ bot communication.

These interfaces decouple business logic from the transport mechanism.
v1 ships with file-based providers. Future versions can swap in
Redis, IPC, sockets, or HTTP without changing callers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from automation.storage.models import AgentEvent, ContextLevel, Instruction


class ContextProvider(ABC):
    """Read/write the agent's current context-window utilisation."""

    @abstractmethod
    def read_level(self) -> Optional[ContextLevel]:
        """Return the latest context level, or None if unavailable."""

    @abstractmethod
    def write_level(self, level: ContextLevel) -> None:
        """Publish a new context level reading."""


class EventProvider(ABC):
    """Emit and consume agent lifecycle events."""

    @abstractmethod
    def emit(self, event: AgentEvent) -> None:
        """Publish an event from the agent side."""

    @abstractmethod
    def read_new(self, after_line: int = 0) -> tuple[list[AgentEvent], int]:
        """Read events not yet consumed.

        Args:
            after_line: file-offset or cursor from the previous call.

        Returns:
            (list_of_new_events, new_cursor) so the caller can resume.
        """


class InstructionProvider(ABC):
    """Send instructions from humans to the agent."""

    @abstractmethod
    def submit(self, instruction: Instruction) -> str:
        """Queue an instruction for the agent. Returns the instruction id."""

    @abstractmethod
    def check_pending(self) -> list[Instruction]:
        """Return all instructions not yet acknowledged by the agent."""

    @abstractmethod
    def acknowledge(self, instruction_id: str) -> None:
        """Mark an instruction as acknowledged by the agent."""

    @abstractmethod
    def write_pause(self) -> None:
        """Signal the agent to pause."""

    @abstractmethod
    def clear_pause(self) -> None:
        """Clear the pause signal."""

    @abstractmethod
    def is_paused(self) -> bool:
        """Check whether a pause signal is active."""
