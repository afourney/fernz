"""Historical V5 behavior measured through public APIs and executables."""

import subprocess

import pytest

from fernz import FernzEnv

from .test_restart_reference import synthetic_reference
from .test_save_restore import results
from .v5_legacy_story import duplicate_story, long_property_story, zero_story

pytestmark = pytest.mark.reference


@pytest.mark.parametrize(
    "image,expected",
    [(duplicate_story(), [11, 9, 33, 99])]
    + [(zero_story(*pair), [2, 1]) for pair in ((0, 2), (1, 0), (0, 0))]
    + [
        (long_property_story(size), [value])
        for size, value in ((3, -31982), (8, -30702), (64, -32750))
    ],
    ids=(
        "duplicate-properties",
        "zero-source",
        "zero-destination",
        "both-zero",
        "long-3",
        "long-8",
        "long-64",
    ),
)
def test_synthetic_legacy_operations_match_both_references(tmp_path, dfrotz, image, expected):
    path = tmp_path / "objects.z5"
    path.write_bytes(image)
    result = subprocess.run(
        [dfrotz, "-q", "-m", "-p", str(path)],
        input="",
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    assert results(result.stdout) == expected
    native = synthetic_reference(path, 42)
    env = FernzEnv(path, seed=42)
    try:
        assert results(native.reset()[0]) == results(env.reset()[0]) == expected
    finally:
        native.close()
        env.close()


@pytest.mark.parametrize(
    "game,boot", (("acorncourt", 0), ("inhumane", 0), ("spirit", 0), ("theatre", 1), ("curses", 1))
)
def test_affected_roms_reach_line_input_and_continue(jericho_games, game, boot):
    from jericho import FrotzEnv

    path = jericho_games / f"{game}.z5"
    native = FrotzEnv(str(path), seed=42)
    env = FernzEnv(path, seed=42)
    try:
        native.reset()
        env.reset()
        for _ in range(boot):
            assert env.get_state().input_request.character
            env.step("")
        for action in (None, "look", "inventory", "wait"):
            if action is not None:
                native.step(action)
                env.step(action)
            actual, expected = env.get_state(), native.get_state()
            assert not actual.input_request.character
            assert actual.input_request.instruction_address == int(expected[2]) - 1
            assert actual.rng.state == int(expected[7][0]) & 0x7FFFFFFF
            objects = env.get_world_objects()
            start = env.story.header.object_table
            end = start + 126 + 14 * (len(objects) - 1)
            assert actual.ram[start:end] == expected[0][start:end].tobytes()
    finally:
        native.close()
        env.close()


@pytest.mark.parametrize("opcode", (0x0B, 0x0C))
@pytest.mark.parametrize("identity", (False, True))
def test_sherlock_identity_attribute_48_write_behavior(tmp_path, dfrotz, opcode, identity):
    from .v5_legacy_story import legacy_story

    data = bytearray(legacy_story(bytes((opcode, 1, 48)) + bytes.fromhex("e5 7f 59 bb ba")))
    if identity:
        data[2:4] = (21).to_bytes(2, "big")
        data[18:24] = b"871214"
    path = tmp_path / "attribute.z5"
    path.write_bytes(data)
    result = subprocess.run(
        [dfrotz, "-q", "-m", "-p", str(path)], input="", capture_output=True, text=True, timeout=15
    )
    assert result.returncode == (0 if identity else 1)
    assert result.stdout == ("Y\n" if identity else "")
    if not identity:
        assert "Illegal attribute" in result.stderr
    reference = synthetic_reference(path, 0)
    try:
        assert reference.reset()[0] == ("Y\n" if identity else "")
    finally:
        reference.close()


def test_cursor_beyond_screen_width_uses_left_margin(tmp_path, dfrotz):
    from .save_story import number
    from .story_files import program_bytes

    # Both reference screens are narrower than 255 columns. Set a valid
    # cursor first, then move off-screen on a different row and query it.
    code = bytes.fromhex("ea 7f 04 eb 7f 01 ef 5f 02 07 ef 5f 03 ff f0 3f 02 50 eb 7f 00")
    code += bytes.fromhex("cf 1f 02 50 00 11") + number(17)
    code += bytes.fromhex("cf 1f 02 50 01 11") + number(17) + b"\xba"
    path = tmp_path / "cursor.z5"
    path.write_bytes(program_bytes(code, version=5))
    result = subprocess.run(
        [dfrotz, "-q", "-m", "-p", str(path)],
        input="",
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    assert results(result.stdout) == [3, 1]
    native = synthetic_reference(path, 42)
    env = FernzEnv(path)
    try:
        assert results(native.reset()[0]) == results(env.reset()[0]) == [3, 1]
    finally:
        native.close()
        env.close()
