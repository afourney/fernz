"""Public story environment with V3 execution through the first input request."""

from os import PathLike
from pathlib import Path

from ._machine import Machine, signed
from ._memory import Memory
from ._story import Story


class FernzEnv:
    """Load a story and expose a small text interaction interface.

    Construction reads a raw V1-V8 story and creates independent memory.
    Successful loading does not establish that the story can be executed yet.
    """

    def __init__(self, game_path: str | PathLike[str], *, seed: int | None = None) -> None:
        """Load a game, raising OSError for I/O or ValueError for invalid input."""
        self.game_path = Path(game_path)
        self.story = Story.from_file(self.game_path)
        self.memory = Memory(self.story)
        self._seed = seed
        self._machine: Machine | None = None

    def reset(self, *, max_steps: int = 250_000) -> tuple[str, dict[str, object]]:
        """Run a fresh V3 episode to its first input request or quit.

        Return the story's output and status globals. Score games expose score
        and moves; time games expose hours and minutes. No input is consumed.
        Other versions and unimplemented opcodes raise NotImplementedError.
        Invalid execution or an exhausted instruction budget raises ExecutionError.
        """
        self._machine = Machine(self.memory, seed=self._seed)
        observation = self._machine.run(max_steps=max_steps)
        second = self._machine.read_variable(17)
        third = self._machine.read_variable(18)
        if self.story.header.flags1 & 2:
            info = {"hours": second, "minutes": third}
        else:
            info = {"score": signed(second), "moves": third}
        return observation, info

    def step(self, action: str) -> tuple[str, int, bool, dict[str, object]]:
        """Return text, reward, done, and metadata for a future text action.

        Currently always raises NotImplementedError; no action is executed.
        """
        raise NotImplementedError("Command input and tokenization are not implemented yet.")

    def close(self) -> None:
        """Release resources; currently an idempotent no-op with no open resources."""
