"""Minimal public environment contract; no story execution is implemented."""

from os import PathLike
from pathlib import Path

from ._memory import Memory
from ._story import Story


class FernzEnv:
    """Load a story and expose the planned text interaction interface.

    Construction reads a raw V1-V8 story and creates independent memory.
    Successful loading does not establish that the story can be executed yet.
    """

    def __init__(self, game_path: str | PathLike[str]) -> None:
        """Load a game, raising OSError for I/O or ValueError for invalid input."""
        self.game_path = Path(game_path)
        self.story = Story.from_file(self.game_path)
        self.memory = Memory(self.story)

    def reset(self) -> tuple[str, dict[str, object]]:
        """Return initial text and metadata once execution is implemented.

        Currently always raises NotImplementedError. No instructions are run.
        """
        raise NotImplementedError("Fernz story execution is not implemented yet.")

    def step(self, action: str) -> tuple[str, int, bool, dict[str, object]]:
        """Return text, reward, done, and metadata for a future text action.

        Currently always raises NotImplementedError; no action is executed.
        """
        raise NotImplementedError("Fernz story execution is not implemented yet.")

    def close(self) -> None:
        """Release resources; currently an idempotent no-op with no open resources."""
