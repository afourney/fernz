"""Public story environment with V3, V4, V5 and V8 text interaction."""

from copy import copy as shallow_copy
from dataclasses import replace
from operator import index
from os import PathLike
from pathlib import Path

from ._errors import ExecutionError
from ._host_io import HostIO, RestoreHandler, SaveHandler
from ._machine import DEFAULT_MAX_STEPS, Machine, signed
from ._memory import Memory
from ._objects import ZObject
from ._observation import Observation
from ._profiles import StoryProfile, profile_for
from ._random import validate_host_seed
from ._state import GameState, StoredInputRequest, _integer
from ._story import Story


class FernzEnv:
    """Load a story and expose a small text interaction interface.

    Construction reads a raw V1-V8 story and creates independent memory.
    Passing an existing Story reuses its immutable image without reopening a
    file and sets game_path to None. Construction never executes the opening.
    Successful loading does not establish that the story can be executed yet.
    A host seed in 0..2**31-1 selects a reproducible sequence; None uses entropy.
    Positive seeds match the tested Jericho/Frotz sequences. Explicit zero is
    deterministic like Frotz's CLI, unlike Jericho's automatic host seed zero.

    save_handler receives Quetzal bytes and returns bool; restore_handler returns
    bytes or None. Missing handlers, cancellation, and OSError report opcode
    failure. reset/step return Observation(stream, text) with output from both
    windows. Storage handlers belong to the receiving environment and are never
    captured or replaced by checkpoints.
    screen_width and screen_height configure a finite display in character cells;
    defaults are 80 by 25. Host checkpoint restore adopts its saved geometry.
    """

    def __init__(
        self,
        game_path: str | PathLike[str] | Story,
        *,
        seed: int | None = None,
        save_handler: SaveHandler | None = None,
        restore_handler: RestoreHandler | None = None,
        screen_width: int = 80,
        screen_height: int = 25,
    ) -> None:
        """Load a path or reuse a Story, creating independent mutable memory."""
        _integer(screen_width, 1, 255, "Screen width")
        _integer(screen_height, 1, 254, "Screen height")
        self._screen_width, self._screen_height = screen_width, screen_height
        self.game_path: Path | None
        if isinstance(game_path, Story):
            self.game_path = None
            self.story = game_path
        else:
            self.game_path = Path(game_path)
            self.story = Story.from_file(self.game_path)
        self.memory = Memory(self.story)
        self._seed = validate_host_seed(seed)
        self._io = HostIO(save_handler, restore_handler)
        self._machine: Machine | None = None
        self._profile = profile_for(self.story)
        self._game_over = False
        self._victory = False

    def seed(self, seed: int | None = None) -> int | None:
        """Select and return the host seed for the next reset(), without executing.

        Accept integers in 0..2**31-1; None selects fresh entropy at reset time.
        Calling without an argument selects None, rather than querying the seed.
        The active RNG, random 0, and in-game restart retain their current host
        policy until reset(). set_state() replaces this choice with its saved seed.
        """
        self._seed = validate_host_seed(seed)
        return self._seed

    @property
    def screen_width(self) -> int:
        """Return the configured display width in fixed-width character cells."""
        return self._screen_width

    @property
    def screen_height(self) -> int:
        """Return the configured display height in character rows."""
        return self._screen_height

    def reset(self, *, max_steps: int = DEFAULT_MAX_STEPS) -> tuple[Observation, dict[str, object]]:
        """Run a fresh supported episode to its first input request or quit.

        Return an Observation with ordered display commands and a plain transcript,
        plus status globals. Score games expose score
        and moves; V3 time games expose hours and minutes. V4/V5/V8 stories without a
        profile return empty info because these versions define no status globals. No input is consumed.
        Other versions and unimplemented opcodes raise NotImplementedError.
        Invalid execution or an exhausted instruction budget raises ExecutionError.
        """
        self._machine = None
        machine = Machine(
            self.memory,
            seed=self._seed,
            io=self._io,
            screen_width=self.screen_width,
            screen_height=self.screen_height,
        )
        observation = machine.run(max_steps=max_steps)
        self._machine = machine
        self._record_outcomes(machine.last_narrative)
        return self._observation(observation), self._info()

    def _observation(self, text: str) -> Observation:
        machine = self._require_machine()
        if (
            self._profile is not None
            and self._profile.strip_command_prompt
            and machine.input_request is not None
            and machine.display.state.window == 0
        ):
            if text.endswith("\n>"):
                text = text[:-1]
            elif text.endswith(" >"):
                text = text[:-2]
        return Observation(
            stream=machine.last_stream, text=text, diagnostics=machine.last_diagnostics
        )

    def _record_outcomes(self, observation: str) -> None:
        self._game_over, self._victory = (
            self._profile.outcomes(observation) if self._profile else (False, False)
        )

    def _require_profile(self) -> StoryProfile:
        if self._profile is None:
            raise NotImplementedError("No story profile is available for this story image")
        return self._profile

    def _require_machine(self) -> Machine:
        if self._machine is None:
            raise RuntimeError("Call reset() or set_state() before reading game status")
        return self._machine

    def _info(self) -> dict[str, int]:
        assert self._machine is not None
        if self._profile is not None:
            profile = self._profile
            if profile.victory_score is not None:
                score = profile.victory_score if self._victory else 0
            else:
                score = self._machine.read_variable(16 + profile.score_global)
                if profile.score_byte:
                    score &= 0xFF
                    if profile.score_signed and score & 0x80:
                        score -= 0x100
                elif profile.score_signed:
                    score = signed(score)
                if profile.score_negated:
                    score = signed(-score & 0xFFFF)
            moves = self._machine.read_variable(16 + profile.moves_global)
            if profile.moves_byte:
                moves &= 0xFF
            return {"score": score, "moves": moves + profile.moves_offset}
        if self.story.header.version >= 4:
            # Later versions have no VM-defined score or move globals (§8).
            return {}
        second = self._machine.read_variable(17)
        third = self._machine.read_variable(18)
        if self.story.header.flags1 & 2:
            info = {"hours": second, "minutes": third}
        else:
            info = {"score": signed(second), "moves": third}
        return info

    def _status_value(self, name: str) -> int:
        self._require_machine()
        if self.story.header.version >= 4 and self._profile is None:
            raise NotImplementedError("Score and move queries require a story profile for V4/V5/V8")
        if self.story.header.flags1 & 2 and self._profile is None:
            raise NotImplementedError("Score and move queries are unavailable for V3 time games")
        return self._info()[name]

    def get_score(self) -> int:
        """Return the profile's score or the standard V3 score, including after quit.

        Require reset() or set_state() after construction or execution failure.
        Unprofiled V4/V5/V8 and V3 time games raise NotImplementedError.
        """
        return self._status_value("score")

    def get_moves(self) -> int:
        """Return the profile's moves or the standard V3 counter, including after quit.

        Require reset() or set_state() after construction or execution failure.
        Unprofiled V4/V5/V8 and V3 time games raise NotImplementedError.
        This reports the story's counter, not the number of host step() calls.
        """
        return self._status_value("moves")

    def get_max_score(self) -> int:
        """Return the known score limit, even before reset or after failure.

        Require a measured fixed score limit; unknown builds and stories without
        a fixed maximum raise NotImplementedError. This is metadata, not a
        value inferred from play.
        """
        maximum = self._require_profile().max_score
        if maximum is None:
            raise NotImplementedError("This story has no fixed maximum score")
        return maximum

    def get_object(self, obj_num: int) -> ZObject | None:
        """Return a detached object, or None for zero or an absent object number.

        Require initialized execution and an enumerable initial object table.
        The result is locally mutable; editing it never writes to the game.
        Non-integer numbers raise TypeError. Malformed object data raises an
        execution or memory error; unsupported table layouts raise NotImplementedError.
        """
        objects = self._require_machine().objects
        number = index(obj_num)
        # Check the version limit first: impossible numbers need no count inference.
        if number < 1 or number > objects.max_number or number > objects.count:
            return None
        return objects.snapshot(number)

    def get_world_objects(self, clean: bool = False) -> list[ZObject]:
        """Return detached objects in number order, with an empty slot zero.

        Include disconnected and invisible objects, not just the current room.
        Enumeration uses the initial layout convention described in §12's
        remarks. Unsupported layouts raise NotImplementedError. Story-specific
        cleaning is deferred; clean=True explicitly raises NotImplementedError.
        """
        objects = self._require_machine().objects
        if clean:
            raise NotImplementedError("Cleaned world-object inspection is not implemented")
        return [
            ZObject(0, "", attr=[0] * objects.attributes),
            *(objects.snapshot(n) for n in range(1, objects.count + 1)),
        ]

    def get_player_object(self) -> ZObject:
        """Return the profile's player as a detached, locally mutable object.

        The Z-machine has no universal player identity. Require initialized
        execution and a story profile that identifies the player.
        """
        objects = self._require_machine().objects
        number = self._require_profile().player_object
        if number is None:
            raise NotImplementedError("No player object is known for this story profile")
        return objects.snapshot(number)

    def get_inventory(self) -> list[ZObject]:
        """Return the player's immediate children, in sibling order.

        Items inside carried containers are not flattened into this list.
        Require a known player. Return independent snapshots and reject cycles
        or inconsistent parent links without changing interpreter state.
        """
        player = self.get_player_object()
        objects = self._require_machine().objects
        inventory = []
        number = player.child
        seen = {player.num}
        while number:
            if number in seen:
                raise ExecutionError("Broken inventory sibling chain")
            seen.add(number)
            obj = objects.snapshot(number)
            if obj.parent != player.num:
                raise ExecutionError("Inconsistent inventory parent link")
            inventory.append(obj)
            number = obj.sibling
        return inventory

    def get_player_location(self) -> ZObject | None:
        """Read the player's location as a complete, detached object snapshot.

        Require reset() or set_state(); work for both score and time games.
        A profile's known player object supplies its immediate parent, which
        can be a vehicle. Otherwise use the V3 status location convention.
        A zero location means unavailable and returns None. Malformed object
        data raises ExecutionError or MemoryAccessError without executing.
        """
        machine = self._require_machine()
        if self._profile is not None and self._profile.player_object is not None:
            number = machine.objects.parent(self._profile.player_object)
        elif self.story.header.version >= 4:
            raise NotImplementedError("Player location requires a story profile for V4/V5/V8")
        else:
            number = machine.read_variable(16)
        return machine.objects.snapshot(number) if number else None

    def game_over(self) -> bool:
        """Whether the latest response reported a loss in a supported story.

        Require initialized state and a story profile. This includes Zork's
        recoverable deaths, clears on an ordinary response, and is independent
        of VM quit. Checkpoints and copies preserve the reported outcome.
        """
        self._require_machine()
        self._require_profile()
        return self._game_over

    def victory(self) -> bool:
        """Whether the latest response reported victory in a supported story.

        Require initialized state and a story profile. A maximum score or quit
        alone does not imply victory. Reading the flag never advances play.
        """
        self._require_machine()
        self._require_profile()
        return self._victory

    def get_state(self) -> GameState:
        """Return an immutable, independent checkpoint after reset() or step().

        Capture RAM, routine frames, PC, pending input, output selection, RNG,
        and response outcomes. Reuse a checkpoint in any FernzEnv for the same story.
        After an execution failure, reset or restore before taking a snapshot.
        """
        if self._machine is None:
            raise RuntimeError("Call reset() or set_state() before get_state()")
        return replace(self._machine.get_state(), game_over=self._game_over, victory=self._victory)

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
        self._screen_width = machine.display.width
        self._screen_height = machine.display.height
        self._game_over, self._victory = state.game_over, state.victory

    def copy(self) -> "FernzEnv":
        """Fork memory, frames, pending input, and RNG without advancing the game.

        Share the immutable story and storage callback references. Storage
        destinations captured by callbacks remain caller-owned. Copying
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
    def initialized(self) -> bool:
        """Whether an execution context exists, including after normal quit.

        False before initialization and after execution failure; successful
        reset() or set_state() makes it true. Query without taking a checkpoint,
        executing instructions, or changing the environment.
        """
        return self._machine is not None

    @property
    def awaiting_character(self) -> bool:
        """Whether a live interpreter is waiting for a single keypress.

        False at a line prompt, before initialization, after quit or execution
        failure. No checkpoint, instruction execution, or RNG draw is involved.
        Pass an empty action for Enter or a literal space for Space to step().
        """
        machine = self._machine
        return (
            machine is not None
            and not machine.halted
            and isinstance(machine.input_request, StoredInputRequest)
            and machine.input_request.character
        )

    @property
    def done(self) -> bool:
        """Whether the current episode has executed quit (not a victory detector)."""
        return self._machine is not None and self._machine.halted

    def step(
        self, action: str, *, max_steps: int = DEFAULT_MAX_STEPS
    ) -> tuple[Observation, int, bool, dict[str, object]]:
        """Submit a line or character and run to the next input request or quit.

        Return new output, score delta (zero for time games), quit status, and
        status globals. Reset or restore a checkpoint before starting play and
        after quit or execution failure.
        Remove line terminators before submitting an action. At a character
        prompt, an empty string means Enter and a literal space means Space;
        only the first character is consumed. Unsupported characters raise
        ValueError without invalidating the current episode. Invalid action
        types and nonpositive/noninteger budgets also preserve it. Errors
        during execution invalidate it; query initialized before recovery.
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
        self._record_outcomes(machine.last_narrative)
        info = self._info()
        return self._observation(observation), info.get("score", 0) - before, self.done, info

    def close(self) -> None:
        """Release resources; currently an idempotent no-op with no open resources."""
