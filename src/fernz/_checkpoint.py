"""Portable JSON codec for the current immutable Fernz checkpoint schema."""

import base64
import json
from dataclasses import asdict, fields
from typing import TypeVar, cast

from ._memory import Memory
from ._state import (
    CHECKPOINT_VERSION,
    ColourPair,
    Cursor,
    FrameState,
    GameState,
    InputRequest,
    MemoryStream,
    OutputState,
    RandomState,
    StoredInputRequest,
    _integer,
)
from ._story import EXECUTABLE_VERSIONS, Story

_Value = TypeVar("_Value")

_FORMAT = "fernz-checkpoint"
_FORMAT_VERSION = 1


def dumps(state: GameState) -> str:
    """Encode a checkpoint as JSON text, with only RAM represented in base64."""
    _integer(
        state.format_version, CHECKPOINT_VERSION, CHECKPOINT_VERSION, "Snapshot format version"
    )
    data = asdict(state)
    del data["format_version"]
    del data["ram"]
    document = {
        "format": _FORMAT,
        "format_version": _FORMAT_VERSION,
        "ram_base64": base64.b64encode(state.ram).decode("ascii"),
        **data,
    }
    return json.dumps(document, ensure_ascii=True, allow_nan=False, indent=2)


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate checkpoint field: {key}")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON number: {value}")


def _value(value: object, cls: type[_Value]) -> _Value:
    # Exact types matter: JSON booleans are not checkpoint integers.
    if type(value) is not cls:
        raise TypeError(f"Expected {cls.__name__} in checkpoint")
    return cast(_Value, value)


def _mapping(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError("Expected a checkpoint object")
    # JSON object keys are strings; values remain untrusted until decoded below.
    return cast(dict[str, object], value)


def _record(value: object, cls: type) -> dict[str, object]:
    record = _mapping(value)
    if record.keys() != {field.name for field in fields(cls)}:
        raise ValueError(f"Expected exactly the fields of {cls.__name__}")
    return record.copy()


def _array(value: object) -> tuple[object, ...]:
    if type(value) is not list:
        raise ValueError("Expected a checkpoint array")
    return tuple(cast(list[object], value))


def _integers(value: object) -> tuple[int, ...]:
    return tuple(_value(item, int) for item in _array(value))


def _optional_integer(value: object) -> int | None:
    return None if value is None else _value(value, int)


def _pair(value: object, cls: type[_Value]) -> tuple[_Value, _Value]:
    left, right = _array(value)
    return _value(left, cls), _value(right, cls)


def _decode(document: object) -> GameState:
    document = _mapping(document)
    if document.pop("format", None) != _FORMAT:
        raise ValueError("Expected a Fernz checkpoint object")
    version = document.get("format_version")
    if type(version) is not int or version != _FORMAT_VERSION:
        raise ValueError(f"Unsupported checkpoint format version: {version!r}")
    expected = {field.name for field in fields(GameState)} - {"ram"} | {"ram_base64"}
    if document.keys() != expected:
        raise ValueError("Expected exactly the fields of a JSON checkpoint")
    ram = base64.b64decode(_value(document["ram_base64"], str), validate=True)

    frames: list[FrameState] = []
    for value in _array(document["frames"]):
        frame = _record(value, FrameState)
        frames.append(
            FrameState(
                locals=_integers(frame["locals"]),
                stack=_integers(frame["stack"]),
                return_address=_optional_integer(frame["return_address"]),
                store=_optional_integer(frame["store"]),
                argument_count=_value(frame["argument_count"], int),
            )
        )

    rng = _record(document["rng"], RandomState)
    python_state = None
    if rng["python_state"] is not None:
        version, words, gaussian = _array(rng["python_state"])
        if gaussian is not None:
            raise ValueError("The integer RNG has no cached Gaussian value")
        python_state = (_value(version, int), _integers(words), None)
    random_state = RandomState(
        host_seed=_optional_integer(rng["host_seed"]),
        state=_value(rng["state"], int),
        period=_value(rng["period"], int),
        position=_value(rng["position"], int),
        python_state=python_state,
    )

    raw_request = document["input_request"]
    request: InputRequest | None = None
    if raw_request is not None:
        cls = StoredInputRequest if "store" in _mapping(raw_request) else InputRequest
        record = _record(raw_request, cls)
        text = _value(record["text"], int)
        parse = _value(record["parse"], int)
        address = _value(record["instruction_address"], int)
        request = (
            StoredInputRequest(
                text,
                parse,
                address,
                _value(record["store"], int),
                _value(record["character"], bool),
            )
            if cls is StoredInputRequest
            else InputRequest(text, parse, address)
        )

    output = _record(document["output"], OutputState)
    cursors: tuple[Cursor, ...] = tuple(_pair(pair, int) for pair in _array(output["cursors"]))
    colours: tuple[ColourPair, ...] = tuple(_pair(pair, str) for pair in _array(output["colours"]))
    streams: tuple[MemoryStream, ...] = tuple(
        _pair(pair, int) for pair in _array(output["memory_streams"])
    )
    output_state = OutputState(
        window=_value(output["window"], int),
        split_lines=_value(output["split_lines"], int),
        cursors=cursors,
        fonts=_pair(output["fonts"], int),
        memory_streams=streams,
        width=_value(output["width"], int),
        height=_value(output["height"], int),
        styles=_pair(output["styles"], int),
        colours=colours,
        buffered=_value(output["buffered"], bool),
    )
    # The public JSON format and in-memory snapshot schema have separate versions.
    # Scalar/shape checks above make construction typed; _validate in loads still
    # checks all ranges and story-specific invariants before exposing the state.
    return GameState(
        story_sha256=_value(document["story_sha256"], str),
        ram=ram,
        pc=_value(document["pc"], int),
        frames=tuple(frames),
        rng=random_state,
        input_request=request,
        screen_enabled=_value(document["screen_enabled"], bool),
        halted=_value(document["halted"], bool),
        format_version=CHECKPOINT_VERSION,
        game_over=_value(document["game_over"], bool),
        victory=_value(document["victory"], bool),
        output=output_state,
    )


def loads(payload: str, story: Story) -> GameState:
    """Validate the wire format and the story-specific continuation off-line."""
    if not isinstance(payload, str):
        raise TypeError("Checkpoint payload must be a JSON string")
    if not isinstance(story, Story):
        raise TypeError("Expected a Story")
    if story.header.version not in EXECUTABLE_VERSIONS:
        raise ValueError("Checkpoint decoding supports V3, V4, V5 and V8")
    try:
        document = json.loads(payload, object_pairs_hook=_object, parse_constant=_constant)
        state = _decode(document)
        state._validate(story)
        # Check protected header fields using separate memory, just as set_state
        # does. Do not construct a Machine, execute, or initialize an RNG here.
        Memory(story)._restore_dynamic(
            state.ram, width=state.output.width, height=state.output.height
        )
    except (ValueError, TypeError, RecursionError) as exc:
        raise ValueError(f"Invalid Fernz checkpoint: {exc}") from exc
    return state
