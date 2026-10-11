"""Restart comparisons through public Jericho APIs and a Frotz executable."""

import warnings

import pytest

from fernz import FernzEnv

from .observation_helpers import plain_text
from .restart_story import restart_story
from .save_story import number
from .story_files import READ, program_bytes
from .test_reference import assert_zork_step
from .test_reference import walkthrough_trace as walkthrough_trace
from .test_reference import zork1 as zork1
from .test_save_reference import run_reference
from .test_save_restore import results

pytestmark = pytest.mark.reference


def synthetic_reference(path, seed):
    from jericho import FrotzEnv

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="Game .* is not fully supported", category=UserWarning
        )
        return FrotzEnv(str(path), seed=seed)


@pytest.mark.parametrize("seed,first", [(42, 14545), (1000, 18626)])
@pytest.mark.parametrize("opcode_seed", [5, 1000])
def test_nested_restart_reseeds_like_both_references(dfrotz, tmp_path, seed, first, opcode_seed):
    story = tmp_path / "restart.z3"
    story.write_bytes(restart_story(opcode_seed=opcode_seed))
    actions = ["descend", "again"] * 2
    expected = [first, 55, first, 55, first]
    # The standalone screen redraw discards the pre-restart R=55 marker;
    # Jericho and Fernz capture it in the current observation. Check both
    # measured renderings explicitly, including every startup RNG draw.
    assert results(run_reference(dfrotz, story, actions, seed=seed)) == [first] * 3
    for env in (FernzEnv(story, seed=seed), synthetic_reference(story, seed)):
        try:
            observations = plain_text(env.reset()[0])
            for action in actions:
                observations += plain_text(env.step(action)[0])
            assert results(observations) == expected
        finally:
            env.close()


def test_restart_preserves_screen_selection_like_both_references(dfrotz, tmp_path):
    story = tmp_path / "streams.z3"
    code = bytes.fromhex("0d 13 0b") + number(19) + bytes.fromhex("f3 7f 01 0d 13 16")
    code += number(19) + READ + bytes.fromhex("f3 3f ff ff b7")
    story.write_bytes(program_bytes(code, (0x100, b"\x00\x01"), (0x85, b"\x00\x90")))
    expected = [11, 22, 22, 22]
    assert results(run_reference(dfrotz, story, ["again", "again"])) == expected
    for env in (FernzEnv(story, seed=42), synthetic_reference(story, 42)):
        try:
            observations = plain_text(env.reset()[0])
            observations += plain_text(env.step("again")[0]) + plain_text(env.step("again")[0])
            assert results(observations) == expected
        finally:
            env.close()


def test_zork_restart_confirmation_checkpoints_and_full_walkthrough(zork1, walkthrough_trace):
    from jericho import FrotzEnv

    seed, actions, _, steps = walkthrough_trace
    env = FernzEnv(zork1, seed=seed)
    reference = FrotzEnv(str(zork1), seed=seed)
    try:
        initial = env.reset()
        reference.reset()
        for action, expected in zip(actions[:35], steps[:35], strict=True):
            assert_zork_step(env.step(action), expected, final=False)
            assert reference.step(action) == expected
        assert steps[34][3]["score"] > 0
        for confirmation in ("no", "yes"):
            actual, expected = env.step("restart"), reference.step("restart")
            # Jericho omits the game's trailing space and '>' at this prompt.
            assert "Do you wish to restart?" in expected[0]
            assert actual[0].text == "\n" + expected[0]
            assert actual[0].stream.endswith(expected[0] + " >")
            assert actual[1:] == expected[1:]
            state, native = env.get_state(), reference.get_state()
            actual, expected = env.step(confirmation), reference.step(confirmation)
            assert_zork_step(actual, expected, final=False)
            if confirmation == "yes":
                assert actual[0].text == "\nRestarting.\n" + initial[0].text
                assert actual[3] == initial[1]
                # A checkpoint at the confirmation still replays the restart.
                env.set_state(state)
                reference.set_state(native)
                assert env.step(confirmation) == actual
                assert reference.step(confirmation) == expected
        for i, (action, expected) in enumerate(zip(actions, steps, strict=True)):
            assert_zork_step(env.step(action), expected, final=i == len(actions) - 1)
            assert reference.step(action) == expected
        assert env.done
        assert reference.victory()
    finally:
        env.close()
        reference.close()
