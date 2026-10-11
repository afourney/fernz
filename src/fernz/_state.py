"""Immutable Fernz checkpoints for deterministic host-side save and restore."""

from dataclasses import dataclass, field
from hashlib import sha256

from ._story import Story


def _integer(value: int, minimum: int, maximum: int, name: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be in {minimum}..{maximum}")


@dataclass(frozen=True, slots=True)
class FrameState:
    """A routine's locals, evaluation stack, and return continuation."""

    locals: tuple[int, ...]
    stack: tuple[int, ...]
    return_address: int | None
    store: int | None
    argument_count: int = 0


@dataclass(frozen=True, slots=True)
class InputRequest:
    """A suspended sread instruction; no input or tokenization has occurred."""

    text: int
    parse: int
    instruction_address: int


@dataclass(frozen=True, slots=True)
class RandomState:
    """Current generator state and the host seed used for subsequent reseeding."""

    host_seed: int | None
    state: int
    period: int
    position: int

    def _validate(self) -> None:
        if self.host_seed is not None:
            _integer(self.host_seed, 0, 2**31 - 1, "RNG host seed")
        _integer(self.state, 0, 2**31 - 1, "RNG state")
        _integer(self.period, 0, 999, "RNG period")
        _integer(self.position, 0, max(0, self.period - 1), "RNG position")


@dataclass(frozen=True, slots=True)
class GameState:
    """A detached checkpoint returned by FernzEnv.get_state().

    RAM contains dynamic memory only, including its current header. Static
    memory comes from the matching story image, identified without file padding.
    Frames, pending input, output selection, randomness, and the most recent
    response's outcome flags complete the schema-2 snapshot. This versioned
    Fernz representation is independent of Jericho's tuple layout
    and of saved-game file formats. Obtain snapshots through the environment.
    """

    story_sha256: str
    ram: bytes = field(repr=False)
    pc: int
    frames: tuple[FrameState, ...]
    rng: RandomState
    input_request: InputRequest | None
    screen_enabled: bool
    halted: bool
    format_version: int = 2
    game_over: bool = False
    victory: bool = False

    def _validate(self, story: Story) -> None:
        _integer(self.format_version, 2, 2, "Snapshot format version")
        if self.story_sha256 != sha256(story.data[: story.size]).hexdigest():
            raise ValueError("Snapshot belongs to a different story image")
        if type(self.ram) is not bytes:
            raise TypeError("Snapshot RAM must be immutable bytes")
        if len(self.ram) != story.header.static_memory:
            raise ValueError("Snapshot RAM has the wrong dynamic-memory length")
        # A final read or quit may leave the PC exactly at the end of the image.
        _integer(self.pc, 0, story.size, "Program counter")
        if type(self.frames) is not tuple:
            raise TypeError("Snapshot frames must be an immutable tuple")
        if not self.frames:
            raise ValueError("Snapshot needs an initial execution frame")
        for number, frame in enumerate(self.frames):
            if type(frame) is not FrameState:
                raise TypeError("Snapshot contains an invalid frame")
            for values in (frame.locals, frame.stack):
                if type(values) is not tuple:
                    raise TypeError("Frame locals and stack must be immutable tuples")
                for value in values:
                    _integer(value, 0, 0xFFFF, "Frame value")
            if len(frame.locals) > 15:
                raise ValueError("A frame cannot have more than 15 locals")
            _integer(frame.argument_count, 0, 3, "V3 argument count")
            if number == 0:
                if (
                    frame.locals
                    or frame.return_address is not None
                    or frame.store is not None
                    or frame.argument_count
                ):
                    raise ValueError("Invalid initial V3 execution frame")
            else:
                _integer(frame.return_address, 0, story.size, "Return address")
                _integer(frame.store, 0, 255, "Return store variable")
        if type(self.rng) is not RandomState:
            raise TypeError("Snapshot contains an invalid RNG state")
        self.rng._validate()
        if type(self.screen_enabled) is not bool or type(self.halted) is not bool:
            raise TypeError("Snapshot output and halt flags must be booleans")
        if type(self.game_over) is not bool or type(self.victory) is not bool:
            raise TypeError("Snapshot outcome flags must be booleans")
        if self.halted:
            if self.input_request is not None:
                raise ValueError("A halted snapshot cannot have pending input")
        else:
            if type(self.input_request) is not InputRequest:
                raise TypeError("A running snapshot must have a pending input request")
            _integer(self.input_request.text, 0, 0xFFFF, "Text buffer address")
            _integer(self.input_request.parse, 0, 0xFFFF, "Parse buffer address")
            _integer(
                self.input_request.instruction_address,
                0,
                story.size - 1,
                "Input instruction address",
            )
