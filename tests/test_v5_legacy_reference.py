"""Historical V5 behavior measured through public APIs and executables."""

import subprocess

import pytest

from fernz import FernzEnv

from .test_restart_reference import synthetic_reference
from .test_save_restore import results
from .v5_legacy_story import duplicate_story, zero_story

pytestmark = pytest.mark.reference


@pytest.mark.parametrize(
    "image,expected",
    [(duplicate_story(), [11, 9, 33, 99])]
    + [(zero_story(*pair), [2, 1]) for pair in ((0, 2), (1, 0), (0, 0))],
    ids=("duplicate-properties", "zero-source", "zero-destination", "both-zero"),
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
