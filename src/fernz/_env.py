"""Public story environment with V3 text interaction."""

from copy import copy as shallow_copy
from operator import index
from os import PathLike
from pathlib import Path

from ._errors import ExecutionError
from ._host_io import HostIO, OutputHandler, RestoreHandler, SaveHandler
from ._machine import Machine, signed
from ._memory import Memory
from ._random import validate_host_seed
from ._state import GameState
from ._story import Story


class FernzEnv:
    """Load a story and expose a small text interaction interface.

    Construction reads a raw V1-V8 story and creates independent memory.
    Successful loading does not establish that the story can be executed yet.
    A host seed in 0..2**31-1 selects a reproducible sequence; None uses entropy.
    Positive seeds match the tested Jericho/Frotz sequences. Explicit zero is
    deterministic like Frotz's CLI, unlike Jericho's automatic host seed zero.

    save_handler receives Quetzal bytes and returns bool; restore_handler returns
    bytes or None. Missing handlers, cancellation, and OSError report opcode
    failure. Optional output_handler receives text fragments during execution;
    reset/step still return the complete observation. Handlers belong to the
    receiving environment and are never captured or replaced by checkpoints.
    """

    def __init__(
        self,
        game_path: str | PathLike[str],
        *,
        seed: int | None = None,
        save_handler: SaveHandler | None = None,
        restore_handler: RestoreHandler | None = None,
        output_handler: OutputHandler | None = None,
    ) -> None:
        """Load a game, raising OSError for I/O or ValueError for invalid input."""
        self.game_path = Path(game_path)
        self.story = Story.from_file(self.game_path)
        self.memory = Memory(self.story)
        self._seed = validate_host_seed(seed)
        self._io = HostIO(save_handler, restore_handler, output_handler)
        self._machine: Machine | None = None

    def seed(self, seed: int | None = None) -> int | None:
        """Select and return the host seed for the next reset(), without executing.

        Accept integers in 0..2**31-1; None selects fresh entropy at reset time.
        Calling without an argument selects None, rather than querying the seed.
        The active RNG, random 0, and in-game restart retain their current host
        policy until reset(). set_state() replaces this choice with its saved seed.
        """
        self._seed = validate_host_seed(seed)
        return self._seed

    def reset(self, *, max_steps: int = 250_000) -> tuple[str, dict[str, object]]:
        """Run a fresh V3 episode to its first input request or quit.

        Return the story's output and status globals. Score games expose score
        and moves; time games expose hours and minutes. No input is consumed.
        Other versions and unimplemented opcodes raise NotImplementedError.
        Invalid execution or an exhausted instruction budget raises ExecutionError.
        """
        self._machine = None
        machine = Machine(self.memory, seed=self._seed, io=self._io)
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

    def _status_value(self, name: str) -> int:
        if self._machine is None:
            raise RuntimeError("Call reset() or set_state() before reading game status")
        if self.story.header.flags1 & 2:
            raise NotImplementedError("Score and move queries are unavailable for V3 time games")
        return self._info()[name]

    def get_score(self) -> int:
        """Return the current signed V3 score, including after quit.

        Require reset() or set_state() after construction or execution failure.
        Time-based V3 games raise NotImplementedError; their info contains time.
        """
        return self._status_value("score")

    def get_moves(self) -> int:
        """Return the current V3 move-count global, including after quit.

        Require reset() or set_state() after construction or execution failure.
        Time-based V3 games raise NotImplementedError; their info contains time.
        This reports the story's counter, not the number of host step() calls.
        """
        return self._status_value("moves")

    def get_state(self) -> GameState:
        """Return an immutable, independent checkpoint after reset() or step().

        Capture RAM, routine frames, PC, pending input, output selection, and
        RNG state. A checkpoint can be reused in any FernzEnv for the same story.
        After an execution failure, reset or restore before taking a snapshot.
        """
        if self._machine is None:
            raise RuntimeError("Call reset() or set_state() before get_state()")
        return self._machine.get_state()

    def set_state(self, state: GameState) -> None:
        """Restore a checkpoint without executing instructions or emitting output.

        Restore the host seed as well as the active random sequence. Accept a
        snapshot before reset, after quit, or after execution failure. Invalid
        states raise TypeError or ValueError without changing the environment.
        This is a host API checkpoint, not the Z-machine restore opcode.
        """
        machine = Machine.from_state(self.memory, state, io=self._io)
        self._machine = machine
        self._seed = state.rng.host_seed

    def copy(self) -> "FernzEnv":
        """Fork memory, frames, pending input, and RNG without advancing the game.

        Share the immutable story and host callback references. Storage and
        output destinations captured by callbacks remain caller-owned. Copying
        neither rereads the ROM nor requests entropy. A pending seed() choice
        is copied separately from the active RNG's host seed.
        An uninitialized or failed environment stays uninitialized in the copy;
        a halted environment stays halted.
        """
        result = shallow_copy(self)
        result.memory = self.memory.copy()
        if self._machine is not None:
            result._machine = Machine.from_state(result.memory, self.get_state(), io=result._io)
        return result

    @property
    def done(self) -> bool:
        """Whether the current episode has executed quit (not a victory detector)."""
        return self._machine is not None and self._machine.halted

    def step(
        self, action: str, *, max_steps: int = 250_000
    ) -> tuple[str, int, bool, dict[str, object]]:
        """Submit one line and run to the next input request or quit.

        Return new output, score delta (zero for time games), quit status, and
        status globals. Reset or restore a checkpoint before starting play and
        after quit or execution failure.
        The action excludes its newline; unsupported characters raise ValueError.
        """
        machine = self._machine
        if machine is None or machine.halted:
            raise RuntimeError(
                "Call reset() or set_state() before step() or after the episode ends or fails"
            )
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
