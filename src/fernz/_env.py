"""Minimal public environment contract; no story execution is implemented."""

from os import PathLike
from pathlib import Path
from stat import S_ISREG


class FernzEnv:
    """Validate a story path and expose the planned text interaction interface.

    Construction checks only that the path identifies a regular file. It does
    not read the story or establish that its format or version is supported.
    """

    def __init__(self, game_path: str | PathLike[str]) -> None:
        """Store a game path, raising OSError or ValueError for invalid paths."""
        self.game_path = Path(game_path)
        if not S_ISREG(self.game_path.stat().st_mode):
            raise ValueError(f"Game path is not a regular file: {self.game_path}")

    def reset(self) -> tuple[str, dict[str, object]]:
        """Return initial text and metadata once execution is implemented.

        Currently always raises NotImplementedError. No story bytes are read.
        """
        raise NotImplementedError("Fernz story execution is not implemented yet.")

    def step(self, action: str) -> tuple[str, int, bool, dict[str, object]]:
        """Return text, reward, done, and metadata for a future text action.

        Currently always raises NotImplementedError; no action is executed.
        """
        raise NotImplementedError("Fernz story execution is not implemented yet.")

    def close(self) -> None:
        """Release resources; currently an idempotent no-op with no open resources."""
