"""A clean-room Z-machine library with V1-V8 loading and V3 startup execution."""

from ._env import FernzEnv
from ._errors import ExecutionError, UnsupportedOpcodeError
from ._memory import Memory, MemoryAccessError
from ._story import Story, StoryFormatError, StoryHeader

__all__ = [
    "ExecutionError",
    "FernzEnv",
    "Memory",
    "MemoryAccessError",
    "Story",
    "StoryFormatError",
    "StoryHeader",
    "UnsupportedOpcodeError",
    "hello",
]


def hello() -> str:
    """Return the package scaffold's greeting."""
    return "Hello from fernz!"
