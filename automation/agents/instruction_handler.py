"""Agent-side instruction handler.

Checks for pending human instructions and provides them to the agent.
Instructions are delivered via the InstructionProvider interface.
"""

from __future__ import annotations

import logging
from typing import Optional

from automation.providers.base import InstructionProvider
from automation.storage.models import Instruction

logger = logging.getLogger("automation.agents.instruction_handler")


class InstructionHandler:
    """Check for and process human instructions from Discord."""

    def __init__(self, provider: InstructionProvider):
        self._provider = provider

    def check_and_acknowledge(self) -> list[Instruction]:
        """Check for pending instructions, acknowledge them, and return them.

        Returns a list of newly-acknowledged instructions.
        """
        pending = self._provider.check_pending()
        acknowledged = []
        for instr in pending:
            try:
                self._provider.acknowledge(instr.id)
                acknowledged.append(instr)
                logger.info(
                    "Acknowledged instruction %s: %s",
                    instr.id, instr.instruction_text[:80],
                )
            except Exception:
                logger.exception("Failed to acknowledge instruction %s", instr.id)
        return acknowledged

    def is_paused(self) -> bool:
        """Check whether the agent should be paused."""
        return self._provider.is_paused()

    def format_for_agent(self, instructions: list[Instruction]) -> str:
        """Format instructions as a text block suitable for feeding to an agent."""
        if not instructions:
            return ""
        parts = ["--- Human Instructions from Discord ---"]
        for instr in instructions:
            parts.append(
                f"\nFrom {instr.discord_username} ({instr.created_at}):\n"
                f"{instr.instruction_text}"
            )
        parts.append("\n--- End Instructions ---")
        return "\n".join(parts)
