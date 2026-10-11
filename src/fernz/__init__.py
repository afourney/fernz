"""A clean-room Z-machine library with V1-V8 loading and V3/V5/V8 text interaction."""

from ._env import FernzEnv
from ._errors import ExecutionError, UnsupportedOpcodeError
from ._memory import Memory, MemoryAccessError
from ._objects import Location, ZObject
from ._observation import Observation
from ._state import GameState
from ._story import Story, StoryFormatError, StoryHeader

__all__ = [
    "ExecutionError",
    "FernzEnv",
    "GameState",
    "Location",
    "Memory",
    "MemoryAccessError",
    "Observation",
    "Story",
    "StoryFormatError",
    "StoryHeader",
    "UnsupportedOpcodeError",
    "ZObject",
    "hello",
]


def hello() -> str:
    """Return the package scaffold's greeting."""
    return "Hello from fernz!"
