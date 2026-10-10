"""Exercise the measured snapshot encoding through public Jericho API calls."""

import re
import warnings
from dataclasses import replace

import pytest

from fernz import FernzEnv

from .state_bridge import MISSING_OBSERVATION, STACK_WORDS, StateBridge
from .story_files import READ, program_bytes

pytestmark = pytest.mark.reference


def call(address, args, store):
    values = (address // 2, *args)
    types = sum((0 if i < len(values) else 3) << (6 - 2 * i) for i in range(4))
    return bytes((0xE0, types)) + b"".join(v.to_bytes(2, "big") for v in values) + bytes((store,))


def number(variable):
    # Print a tagged numeric result from a variable. Stack variable zero pops.
    return bytes.fromhex("e5 7f 52 e5 7f 3d e6 bf") + bytes((variable, 0xBB))


def random(operand):
    return bytes.fromhex("e7 3f") + (operand & 65535).to_bytes(2, "big") + b"\x1f"


def probe_story(locals_count=3, args=(), read_kind="constant", mode="counting", high=False):
    outer_address = 0x11000 if high else 0x900
    root = bytes.fromhex("e8 3f 11 11") + call(outer_address, (0xAAAA,), 17)
    root += number(17) + number(0) + READ + b"\xba"
    # A caller with locals, a stack value, and its own input after the child
    # returns. With high=True, both its saved return PC and its read exceed 64K.
    outer = bytes.fromhex("01 12 34 e8 3f 44 44") + call(0x600, args, 1)
    outer += number(1) + number(0) + READ + bytes.fromhex("ab 01")
    inner = bytes((locals_count,))
    inner += b"".join((0x2200 + i).to_bytes(2, "big") for i in range(locals_count))
    inner += bytes.fromhex("e8 3f 33 33")
    if mode == "counting":
        inner += random(-5)
    elif mode == "affine":
        inner += random(-1000)
    inner += random(6) * 2
    if mode == "switch":
        inner += random(-5) + random(6) * 2 + random(-1000)
    if read_kind == "stack":
        inner += bytes.fromhex("e8 3f 02 a0 e8 3f 02 80 e4 af 00 00")
    elif read_kind == "global":
        inner += bytes.fromhex("e4 af 18 19")
    elif read_kind == "local":
        inner += bytes.fromhex("cd 4f 01 02 80 cd 4f 02 02 a0 e4 af 01 02")
    else:
        inner += READ
    for variable in range(1, locals_count + 1):
        inner += number(variable)
    inner += number(0)
    inner += (random(32767) + number(31)) * 10
    inner += random(0) + random(32767) + number(31) + bytes.fromhex("9b 2a")
    return program_bytes(
        root,
        (0x600, inner),
        (outer_address, outer),
        (0x100, b"\x00\x01"),  # Valid current-room object for native status output.
        (0x85, b"\x00\x90"),
        (0x110, b"\x02\x80\x02\xa0"),  # Globals 24/25 hold the input addresses.
        size=0x12000 if high else 4096,
    )


def reference_env(path, seed=42):
    from jericho import FrotzEnv

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="Game .* is not fully supported", category=UserWarning
        )
        return FrotzEnv(str(path), seed=seed)


def results(observation):
    return [int(n) for n in re.findall(r"^R=(-?\d+)$", observation, re.MULTILINE)]


@pytest.mark.parametrize("direction", ("jericho_to_fernz", "fernz_to_jericho"))
@pytest.mark.parametrize(
    "locals_count,args,read_kind,mode,high",
    [
        (0, (), "constant", "host", False),
        (0, (7, 8, 9), "stack", "counting", False),
        (1, (), "constant", "affine", False),
        (3, (0xABCD,), "global", "switch", False),
        (3, (0xABCD, 0xBCDE, 0xCDEF), "local", "affine", False),
        (15, (0xABCD, 0xBCDE, 0xCDEF), "stack", "counting", False),
        (3, (0xABCD,), "stack", "affine", True),
    ],
)
def test_synthetic_state_transfer(tmp_path, direction, locals_count, args, read_kind, mode, high):
    path = tmp_path / "exchange.z3"
    path.write_bytes(probe_story(locals_count, args, read_kind, mode, high))
    reference = reference_env(path)
    env = FernzEnv(path, seed=42)
    try:
        reference.reset()
        env.reset()
        bridge = StateBridge(env.story, reference.get_state(), seed=42)
        # Check the measured stack layout against independently assembled calls,
        # not just against a serializer/deserializer round trip.
        measured = bridge.from_jericho(reference.get_state())
        original = env.get_state()
        assert measured.frames == original.frames
        assert measured.pc == original.pc
        assert measured.input_request == original.input_request
        assert measured.ram == original.ram
        assert measured.frames[-1].argument_count == len(args)
        assert len(measured.frames[-1].locals) == locals_count
        for stage in range(3):
            if direction == "jericho_to_fernz":
                env = FernzEnv(path, seed=1)  # Fresh recipient; no prefix execution.
                env.set_state(bridge.from_jericho(reference.get_state()))
            else:
                native = bridge.to_jericho(env.get_state())
                assert native[8] == MISSING_OBSERVATION
                reference.reset()  # Discard recipient state before importing.
                reference.set_state(native)
            actual = results(env.step("look")[0])
            expected = results(reference.step("look")[0])
            assert actual == expected
            assert len(actual) == (locals_count + 14 if stage == 0 else 2 if stage == 1 else 0)
            if stage == 0:
                assert actual[locals_count] == 0x3333
                assert actual[-2:] == [42, 0x4444]
            if stage == 1:
                assert actual == [42, 0x1111]
        assert env.done
    finally:
        env.close()
        reference.close()


@pytest.fixture
def paused(tmp_path):
    path = tmp_path / "exchange.z3"
    path.write_bytes(probe_story())
    reference = reference_env(path)
    env = FernzEnv(path, seed=42)
    try:
        reference.reset()
        env.reset()
        native = reference.get_state()
        yield StateBridge(env.story, native, seed=42), env.get_state(), native
    finally:
        env.close()
        reference.close()


@pytest.mark.parametrize(
    "field,value",
    [(2, 0), (3, -1), (4, 1025), (5, 0), (5, 256), (6, 0xBA), (7, (42, 5, 5))],
)
def test_invalid_native_registers_are_rejected(paused, field, value):
    bridge, _, native = paused
    malformed = list(native)
    malformed[field] = value
    with pytest.raises(ValueError):
        bridge.from_jericho(tuple(malformed))


def test_native_array_shapes_and_frame_links_are_checked(paused):
    bridge, _, native = paused
    for field in (0, 1):
        malformed = list(native)
        malformed[field] = malformed[field][:-1]
        with pytest.raises(ValueError, match="array"):
            bridge.from_jericho(tuple(malformed))
    malformed = list(native)
    malformed[1] = native[1].copy()
    fp = native[4]
    malformed[1][2 * (fp + 1) : 2 * (fp + 2)] = [0, 0]
    with pytest.raises(ValueError, match="parent-frame"):
        bridge.from_jericho(tuple(malformed))


def test_unsupported_fernz_states_are_rejected(paused):
    bridge, state, _ = paused
    for malformed in (
        replace(state, halted=True, input_request=None),
        replace(state, screen_enabled=False),
        replace(state, rng=replace(state.rng, host_seed=99)),
        replace(state, pc=state.pc + 1),
        replace(state, input_request=replace(state.input_request, text=0x290)),
        replace(state, frames=(replace(state.frames[0], stack=(1,) * (STACK_WORDS + 1)),)),
    ):
        with pytest.raises(ValueError):
            bridge.to_jericho(malformed)
