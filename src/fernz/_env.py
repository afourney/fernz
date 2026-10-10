"""Public story environment with V3 text interaction."""

from operator import index
from os import PathLike
from pathlib import Path

from ._errors import ExecutionError
from ._machine import Machine, signed
from ._memory import Memory
from ._story import Story


class FernzEnv:
    """Load a story and expose a small text interaction interface.

    Construction reads a raw V1-V8 story and creates independent memory.
    Successful loading does not establish that the story can be executed yet.
    A host seed in 0..2**31-1 selects a reproducible sequence; None uses entropy.
    Positive seeds match the tested Jericho/Frotz sequences. Explicit zero is
    deterministic like Frotz's CLI, unlike Jericho's automatic host seed zero.
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
        self._machine = None
        machine = Machine(self.memory, seed=self._seed)
        observation = machine.run(max_steps=max_steps)
        self._machine = machine
        return observation, self._info()

    def _info(self) -> dict[str, int]:
        assert self._machine is not None
        second = self._machine.read_variable(17)
        third = self._machine.read_variable(18)
        if self.story.header.flags1 & 2:
            info = {"hours": second, "minutes": third}
        else:
            info = {"score": signed(second), "moves": third}
        return info

    @property
    def done(self) -> bool:
        """Whether the current episode has executed quit (not a victory detector)."""
        return self._machine is not None and self._machine.halted

    def step(
        self, action: str, *, max_steps: int = 250_000
    ) -> tuple[str, int, bool, dict[str, object]]:
        """Submit one line and run to the next input request or quit.

        Return new output, score delta (zero for time games), quit status, and
        status globals. Call reset first and after quit or execution failure.
        The action excludes its newline; unsupported characters raise ValueError.
        """
        machine = self._machine
        if machine is None or machine.halted:
            raise RuntimeError("Call reset() before step() or after the episode ends or fails")
        max_steps = index(max_steps)
        if max_steps <= 0:
            raise ValueError("max_steps must be positive")
        before = self._info().get("score", 0)
        try:
            machine.accept_input(action)
        except ExecutionError:
            self._machine = None
            raise
        self._machine = None  # Execution failure requires a fresh episode.
        observation = machine.run(max_steps=max_steps)
        self._machine = machine
        info = self._info()
        return observation, info.get("score", 0) - before, self.done, info

    def close(self) -> None:
        """Release resources; currently an idempotent no-op with no open resources."""
