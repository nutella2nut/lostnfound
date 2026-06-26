"""Provider interfaces and default file-based implementations."""

from automation.providers.base import ContextProvider, EventProvider, InstructionProvider
from automation.providers.file import (
    FileContextProvider,
    FileEventProvider,
    FileInstructionProvider,
)

__all__ = [
    "ContextProvider",
    "EventProvider",
    "InstructionProvider",
    "FileContextProvider",
    "FileEventProvider",
    "FileInstructionProvider",
]
