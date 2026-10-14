"""Portable JSON codec for the current immutable Fernz checkpoint schema."""

import base64
import json
from dataclasses import asdict, fields
from typing import Any

from ._memory import Memory
from ._state import (
    CHECKPOINT_VERSION,
    FrameState,
    GameState,
    InputRequest,
    OutputState,
    RandomState,
    StoredInputRequest,
    _integer,
)
from ._story import EXECUTABLE_VERSIONS, Story

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


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate checkpoint field: {key}")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON number: {value}")


def _record(value: Any, cls: type) -> dict[str, Any]:
    if type(value) is not dict or value.keys() != {field.name for field in fields(cls)}:
        raise ValueError(f"Expected exactly the fields of {cls.__name__}")
    return value.copy()


def _array(value: Any) -> tuple:
    if type(value) is not list:
        raise ValueError("Expected a checkpoint array")
    return tuple(value)


def _decode(document: Any) -> GameState:
    if type(document) is not dict or document.pop("format", None) != _FORMAT:
        raise ValueError("Expected a Fernz checkpoint object")
    version = document.get("format_version")
    if type(version) is not int or version != _FORMAT_VERSION:
        raise ValueError(f"Unsupported checkpoint format version: {version!r}")
    expected = {field.name for field in fields(GameState)} - {"ram"} | {"ram_base64"}
    if document.keys() != expected:
        raise ValueError("Expected exactly the fields of a JSON checkpoint")
    document["ram"] = document.pop("ram_base64")
    # The public JSON format and in-memory snapshot schema have separate versions.
    document["format_version"] = CHECKPOINT_VERSION
    data = _record(document, GameState)
    if type(data["ram"]) is not str:
        raise ValueError("Checkpoint RAM must be a base64 string")
    data["ram"] = base64.b64decode(data["ram"], validate=True)

    frames = []
    for value in _array(data["frames"]):
        frame = _record(value, FrameState)
        frame["locals"] = _array(frame["locals"])
        frame["stack"] = _array(frame["stack"])
        frames.append(FrameState(**frame))
    data["frames"] = tuple(frames)

    rng = _record(data["rng"], RandomState)
    if rng["python_state"] is not None:
        version, words, gaussian = _array(rng["python_state"])
        rng["python_state"] = (version, _array(words), gaussian)
    data["rng"] = RandomState(**rng)

    request = data["input_request"]
    if request is not None:
        cls = StoredInputRequest if type(request) is dict and "store" in request else InputRequest
        data["input_request"] = cls(**_record(request, cls))

    output = _record(data["output"], OutputState)
    for name in ("fonts", "styles"):
        output[name] = _array(output[name])
    for name in ("cursors", "colours", "memory_streams"):
        output[name] = tuple(_array(pair) for pair in _array(output[name]))
    data["output"] = OutputState(**output)
    return GameState(**data)


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
