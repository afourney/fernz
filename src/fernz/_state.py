"""Immutable Fernz checkpoints for deterministic host-side save and restore."""

from dataclasses import dataclass, field
from hashlib import sha256

from ._observation import COLOURS
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
class StoredInputRequest(InputRequest):
    """A V5+ line read or V4+ character read with its decoded result variable."""

    store: int
    character: bool = False


@dataclass(frozen=True, slots=True)
class OutputState:
    """Logical text windows and nested memory-output continuations."""

    window: int = 0
    split_lines: int = 0
    cursors: tuple[tuple[int, int], ...] = ((1, 1), (1, 1))
    fonts: tuple[int, int] = (1, 1)
    memory_streams: tuple[tuple[int, int], ...] = ()
    width: int = 80
    height: int = 25
    styles: tuple[int, int] = (0, 0)
    colours: tuple[tuple[str, str], ...] = (("white", "black"), ("white", "black"))
    buffered: bool = True

    def _validate(self, story: Story) -> None:
        _integer(self.window, 0, 1, "Selected window")
        _integer(self.width, 1, 255, "Screen width")
        _integer(self.height, 1, 254, "Screen height")
        _integer(self.split_lines, 0, self.height, "Upper window height")
        if type(self.cursors) is not tuple or len(self.cursors) != 2:
            raise TypeError("Expected two immutable window cursors")
        for cursor in self.cursors:
            if type(cursor) is not tuple or len(cursor) != 2:
                raise TypeError("Expected an immutable row/column cursor")
            _integer(cursor[0], 1, self.height, "Cursor row")
            _integer(cursor[1], 1, self.width + 1, "Cursor column")
        if type(self.fonts) is not tuple or len(self.fonts) != 2:
            raise TypeError("Expected two immutable font selections")
        if any(type(font) is not int or font not in (1, 4) for font in self.fonts):
            raise ValueError("Unsupported text font")
        if type(self.styles) is not tuple or len(self.styles) != 2:
            raise TypeError("Expected two immutable text styles")
        for style in self.styles:
            _integer(style, 0, 15, "Text style")
        if type(self.colours) is not tuple or len(self.colours) != 2:
            raise TypeError("Expected two immutable colour pairs")
        for pair in self.colours:
            if type(pair) is not tuple or len(pair) != 2:
                raise TypeError("Expected an immutable foreground/background pair")
            for colour in pair:
                if type(colour) is not str or not (
                    colour in COLOURS
                    or (
                        len(colour) == 7
                        and colour[0] == "#"
                        and all(c in "0123456789abcdef" for c in colour[1:])
                    )
                ):
                    raise ValueError("Invalid display colour")
        if type(self.buffered) is not bool:
            raise TypeError("Output buffering must be a boolean")
        if type(self.memory_streams) is not tuple or len(self.memory_streams) > 16:
            raise TypeError("Expected at most 16 immutable memory streams")
        for stream in self.memory_streams:
            if type(stream) is not tuple or len(stream) != 2:
                raise TypeError("Expected an immutable memory stream")
            address, count = stream
            _integer(address, 64, story.header.static_memory - 2, "Output table")
            _integer(count, 0, story.header.static_memory - address - 2, "Output count")


@dataclass(frozen=True, slots=True)
class RandomState:
    """Current generator state and the host seed used for subsequent reseeding."""

    host_seed: int | None
    state: int
    period: int
    position: int
    python_state: tuple[int, tuple[int, ...], None] | None = field(default=None, repr=False)

    def _validate(self) -> None:
        if self.host_seed is not None:
            _integer(self.host_seed, 0, 2**31 - 1, "RNG host seed")
        _integer(self.state, 0, 2**31 - 1, "RNG state")
        _integer(self.period, 0, 999, "RNG period")
        _integer(self.position, 0, max(0, self.period - 1), "RNG position")
        if self.python_state is not None:
            if self.host_seed is not None or self.state or self.period or self.position:
                raise ValueError("Python RNG state cannot include a predictable generator")
            if type(self.python_state) is not tuple or len(self.python_state) != 3:
                raise TypeError("Expected an immutable Python RNG state")
            version, words, gaussian = self.python_state
            _integer(version, 3, 3, "Python RNG state version")
            if type(words) is not tuple or len(words) != 625:
                raise TypeError("Expected 624 immutable Python RNG words and an index")
            for word in words[:-1]:
                _integer(word, 0, 0xFFFFFFFF, "Python RNG word")
            _integer(words[-1], 0, 624, "Python RNG index")
            if gaussian is not None:
                raise ValueError("The integer RNG has no cached Gaussian value")


@dataclass(frozen=True, slots=True)
class GameState:
    """Immutable schema-5 checkpoint at a public input or quit boundary.

    RAM contains dynamic memory only, including its current header. Static
    memory comes from the matching story image, identified without file padding.
    Frames, pending input, logical display state, randomness, and the most recent
    response's outcome flags preserve the complete execution continuation.
    This versioned representation is independent of Jericho's tuple layout
    and saved-game file formats. Obtain snapshots through the environment.
    """

    story_sha256: str
    ram: bytes = field(repr=False)
    pc: int
    frames: tuple[FrameState, ...]
    rng: RandomState
    input_request: InputRequest | None
    screen_enabled: bool
    halted: bool
    format_version: int = 5
    game_over: bool = False
    victory: bool = False
    output: OutputState = OutputState()

    def _validate(self, story: Story) -> None:
        _integer(self.format_version, 5, 5, "Snapshot format version")
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
            _integer(
                frame.argument_count, 0, 3 if story.header.version == 3 else 7, "Argument count"
            )
            if number == 0:
                if (
                    frame.locals
                    or frame.return_address is not None
                    or frame.store is not None
                    or frame.argument_count
                ):
                    raise ValueError("Invalid initial execution frame")
            else:
                _integer(frame.return_address, 0, story.size, "Return address")
                if frame.store is not None or story.header.version == 3:
                    _integer(frame.store, 0, 255, "Return store variable")
        if type(self.rng) is not RandomState:
            raise TypeError("Snapshot contains an invalid RNG state")
        self.rng._validate()
        if type(self.output) is not OutputState:
            raise TypeError("Snapshot contains an invalid output state")
        self.output._validate(story)
        if type(self.screen_enabled) is not bool or type(self.halted) is not bool:
            raise TypeError("Snapshot output and halt flags must be booleans")
        if type(self.game_over) is not bool or type(self.victory) is not bool:
            raise TypeError("Snapshot outcome flags must be booleans")
        if self.halted:
            if self.input_request is not None:
                raise ValueError("A halted snapshot cannot have pending input")
        else:
            if type(self.input_request) not in (InputRequest, StoredInputRequest):
                raise TypeError("A running snapshot must have a pending input request")
            if type(self.input_request) is StoredInputRequest:
                _integer(self.input_request.store, 0, 255, "Input result variable")
                if type(self.input_request.character) is not bool:
                    raise TypeError("Character-input flag must be a boolean")
                if story.header.version < (4 if self.input_request.character else 5):
                    raise ValueError("Stored input requires V5+, or a V4 character read")
            elif story.header.version >= 5:
                raise ValueError("V5 input must have a result variable")
            _integer(self.input_request.text, 0, 0xFFFF, "Text buffer address")
            _integer(self.input_request.parse, 0, 0xFFFF, "Parse buffer address")
            _integer(
                self.input_request.instruction_address,
                0,
                story.size - 1,
                "Input instruction address",
            )
