"""A clean-room Z-machine library with V1-V8 story loading."""

from ._env import FernzEnv
from ._memory import Memory, MemoryAccessError
from ._story import Story, StoryFormatError, StoryHeader

__all__ = [
    "FernzEnv",
    "Memory",
    "MemoryAccessError",
    "Story",
    "StoryFormatError",
    "StoryHeader",
    "hello",
]


def hello() -> str:
    """Return the package scaffold's greeting."""
    return "Hello from fernz!"
