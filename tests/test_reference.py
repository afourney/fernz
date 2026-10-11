"""Black-box API comparisons: never inspect Jericho or Frotz implementation code."""

import hashlib

import pytest

from fernz import ExecutionError, FernzEnv

from .zork_scenarios import ZORK1_SHA256

pytestmark = pytest.mark.reference

ACTIONS = ("look", "open mailbox", "take leaflet", "read leaflet", "inventory")


@pytest.fixture(scope="module")
def zork1(jericho_games):
    story = jericho_games / "zork1.z5"
    data = story.read_bytes()
    assert hashlib.sha256(data).hexdigest() == ZORK1_SHA256, "Unexpected Zork I fixture"
    assert data[0] == 3  # Detect the version from the header, not the extension.
    return story


@pytest.fixture(scope="module")
def reference_trace(zork1):
    # Import only when selected: normal tests need neither Jericho nor the ROMs.
    # Use documented public calls only; no reflection or native-library access.
    from jericho import FrotzEnv

    env = FrotzEnv(str(zork1), seed=42)
    try:
        initial = env.reset()
        steps = [env.step(action) for action in ACTIONS]
        assert env.reset() == initial, "Jericho reset did not restore the opening"
        assert [env.step(action) for action in ACTIONS] == steps, "Unstable reference trace"
        return initial, steps
    finally:
        env.close()


@pytest.fixture(scope="module")
def walkthrough_trace(zork1):
    from jericho import FrotzEnv

    # Both the walkthrough and its seed come from documented public calls.
    # Pin their dimensions along with the ROM hash and Jericho version so
    # upstream changes require investigation instead of weakening coverage.
    env = FrotzEnv(str(zork1))
    try:
        seed = env.seed()
        actions = env.get_walkthrough()
        assert seed == 12
        assert len(actions) == 396
        initial = env.reset()  # Apply the seed before recording any output.
        steps = [env.step(action) for action in actions]
        assert all(step[2] is False for step in steps[:-1])
        assert steps[-1][2] is True
        assert env.victory() is True
        assert env.get_score() == env.get_max_score() == 350
        assert env.get_moves() == 395
        assert env.reset() == initial, "Jericho reset did not restore the opening"
        assert [env.step(action) for action in actions] == steps, "Unstable walkthrough trace"
        assert env.victory() is True
        return seed, actions, initial, steps
    finally:
        env.close()


def assert_observation(actual, expected):
    # Accommodate platform line endings only; do not erase gameplay differences.
    assert isinstance(actual, str)
    assert actual.replace("\r\n", "\n") == expected.replace("\r\n", "\n")


def assert_info(actual, expected):
    assert isinstance(actual, dict)
    for key in ("score", "moves"):
        assert type(actual[key]) is int
        assert actual[key] == expected[key], key


def assert_zork_opening(actual, expected):
    # Black-box observation: Jericho 3.3.1 omits this recognized game's title
    # and its final prompt. Preserve both in Fernz; compare every remaining byte.
    # These explicit assertions keep a lost title or prompt from passing unnoticed.
    title = "ZORK I: The Great Underground Empire\n"
    assert actual.startswith(title)
    assert actual.endswith("\n>")
    assert_observation(actual.removeprefix(title).removesuffix(">"), expected)


def assert_zork_turn(actual, expected):
    # Jericho omits the input Enter newline and the story's prompt. Assert both
    # explicitly before comparing the complete remaining response.
    assert actual.startswith("\n")
    assert actual.endswith("\n>")
    assert_observation(actual.removeprefix("\n").removesuffix(">"), expected)


def assert_zork_step(actual, expected, *, final):
    observation, reward, done, info = actual
    assert type(reward) is int
    assert reward == expected[1]
    assert type(done) is bool
    assert done == expected[2]
    if not final:
        assert_zork_turn(observation, expected[0])
        assert_info(info, expected[3])
    else:
        # This ending executes quit. Black-box Jericho adds one final newline
        # and reports 395 moves; the story prints 394. Fernz stops at quit and
        # returns the status global (394), as in the standalone Frotz ending.
        # Assert these exact differences only on the final turn.
        assert observation.startswith("\n")
        assert observation.endswith("\n")
        assert expected[0].endswith("\n\n")
        assert_observation(observation.removeprefix("\n") + "\n", expected[0])
        assert_info(info, {"score": 350, "moves": 394})
        assert_info(expected[3], {"score": 350, "moves": 395})


def test_jericho_reference_runs(reference_trace):
    """Fail independently if the reference cannot run the pinned Zork I story."""
    (observation, info), steps = reference_trace
    assert "West of House" in observation
    assert info["score"] == 0
    assert info["moves"] == 0
    assert "leaflet" in steps[1][0].lower()
    assert "leaflet" in steps[-1][0].lower()
    for observation, reward, done, info in steps:
        assert isinstance(observation, str)
        assert reward == 0
        assert done is False
        assert info["score"] == 0
    assert steps[-1][3]["moves"] > 0


def test_zork1_reset_matches_jericho(zork1, reference_trace):
    expected, _ = reference_trace
    env = FernzEnv(zork1, seed=42)
    try:
        for _ in range(2):
            observation, info = env.reset()
            assert_zork_opening(observation, expected[0])
            assert_info(info, expected[1])
            env.memory.write_word(env.story.header.globals_table + 2, 0xFFFF)
    finally:
        env.close()


def test_zork1_short_sequence_matches_jericho(zork1, reference_trace):
    initial, expected_steps = reference_trace
    env = FernzEnv(zork1, seed=42)
    try:
        # Compare two episodes to exercise reset after play as well as fresh reset.
        for _ in range(2):
            observation, info = env.reset()
            assert_zork_opening(observation, initial[0])
            assert_info(info, initial[1])
            for action, expected in zip(ACTIONS, expected_steps, strict=True):
                observation, reward, done, info = env.step(action)
                assert_zork_turn(observation, expected[0])
                assert type(reward) is int
                assert reward == expected[1], action
                assert type(done) is bool
                assert done == expected[2], action
                assert_info(info, expected[3])
    finally:
        env.close()


def test_zork1_command_parsing_matches_jericho(zork1):
    from jericho import FrotzEnv

    reference = FrotzEnv(str(zork1), seed=42)
    env = FernzEnv(zork1, seed=42)
    try:
        reference.reset()
        env.reset()
        for action in (
            "LoOk",
            "  OPEN   MAILBOX  ",
            "take leaflets",
            "read leaflet",
            "xyzzy",
            "look,look",
            "inventory",
        ):
            actual = env.step(action)
            expected = reference.step(action)
            assert_zork_turn(actual[0], expected[0])
            assert actual[1:3] == expected[1:3]
            assert_info(actual[3], expected[3])
    finally:
        env.close()
        reference.close()


def test_zork1_full_walkthrough_matches_jericho(zork1, walkthrough_trace):
    seed, actions, initial, steps = walkthrough_trace
    env = FernzEnv(zork1, seed=seed)
    try:
        for episode in range(1, 3):
            observation, info = env.reset()
            assert_zork_opening(observation, initial[0])
            assert_info(info, initial[1])
            for turn, (action, expected) in enumerate(zip(actions, steps, strict=True), 1):
                try:
                    assert_zork_step(env.step(action), expected, final=turn == len(actions))
                except (AssertionError, ExecutionError, NotImplementedError) as error:
                    error.add_note(f"Walkthrough episode {episode}, turn {turn}: {action!r}")
                    raise
            assert env.done is True
    finally:
        env.close()


def test_zork1_checkpoint_replay_matches_jericho(zork1, walkthrough_trace):
    from jericho import FrotzEnv

    seed, actions, initial, steps = walkthrough_trace
    reference = FrotzEnv(str(zork1), seed=seed)
    env = FernzEnv(zork1, seed=seed)
    try:
        assert reference.reset() == initial
        observation, info = env.reset()
        assert_zork_opening(observation, initial[0])
        assert_info(info, initial[1])
        for turn, (action, expected) in enumerate(zip(actions, steps, strict=True), 1):
            try:
                # Treat Jericho's returned snapshot as opaque: give it back only
                # through set_state(). Fernz has its own immutable representation.
                reference_state = reference.get_state()
                state = env.get_state()
                assert reference.step(action) == expected
                actual = env.step(action)
                assert_zork_step(actual, expected, final=turn == len(actions))
                assert reference.set_state(reference_state) is None
                assert env.set_state(state) is None
                assert env.get_state() == state
                assert reference.step(action) == expected, "Jericho restore changed the result"
                assert env.step(action) == actual, "Fernz restore changed the result"
            except (
                AssertionError,
                ExecutionError,
                NotImplementedError,
                TypeError,
                ValueError,
            ) as error:
                error.add_note(f"Checkpoint replay at turn {turn}: {action!r}")
                raise
        assert reference.victory() is True
        assert env.done is True
    finally:
        env.close()
        reference.close()


@pytest.mark.parametrize("direction", ("jericho_to_fernz", "fernz_to_jericho"))
@pytest.mark.parametrize("checkpoint", (35, 214, 350))
def test_zork1_cross_interpreter_continuation(zork1, walkthrough_trace, direction, checkpoint):
    from jericho import FrotzEnv

    from .state_bridge import StateBridge

    seed, actions, initial, steps = walkthrough_trace
    reference = FrotzEnv(str(zork1), seed=seed)
    env = FernzEnv(zork1, seed=seed)
    try:
        assert reference.reset() == initial
        bridge = StateBridge(env.story, reference.get_state(), seed=seed)
        # Only the donor plays the prefix. The recipient starts from an imported
        # snapshot; it then plays the entire remaining route without another import.
        if direction == "jericho_to_fernz":
            for action, expected in zip(actions[:checkpoint], steps[:checkpoint], strict=True):
                assert reference.step(action) == expected
            env.set_state(bridge.from_jericho(reference.get_state()))
        else:
            env.reset()
            for action, expected in zip(actions[:checkpoint], steps[:checkpoint], strict=True):
                assert_zork_step(env.step(action), expected, final=False)
            reference.set_state(bridge.to_jericho(env.get_state()))
        for turn in range(checkpoint, len(actions)):
            try:
                assert reference.step(actions[turn]) == steps[turn]
                assert_zork_step(
                    env.step(actions[turn]), steps[turn], final=turn == len(actions) - 1
                )
            except (AssertionError, ExecutionError, NotImplementedError) as error:
                error.add_note(
                    f"{direction}, checkpoint {checkpoint}, turn {turn + 1}: {actions[turn]!r}"
                )
                raise
        assert env.done
        assert reference.victory() is True
    finally:
        env.close()
        reference.close()


def test_zork1_walkthrough_with_save_restore_opcodes(zork1, walkthrough_trace):
    from .test_save_restore import Storage

    seed, actions, initial, steps = walkthrough_trace
    storage = Storage()
    env = FernzEnv(zork1, seed=seed, save_handler=storage.save, restore_handler=storage.restore)
    try:
        assert_zork_opening(env.reset()[0], initial[0])
        for turn, (action, expected) in enumerate(zip(actions, steps, strict=True)):
            if turn in (35, 214, 350):
                before = env.get_state()
                info = env._info()
                assert env.step("save")[0] == "\nOk.\n\n>"
                assert env.get_state().rng == before.rng
                # Change real gameplay memory without taking a turn or drawing
                # randomness. Restoring must recover it from the saved file.
                score_address = env.story.header.globals_table + 2
                env.memory.write_word(score_address, (info["score"] + 123) & 0xFFFF)
                observation, _, done, restored_info = env.step("restore")
                assert observation == "\nOk.\n\n>"
                assert not done
                assert restored_info == info
                assert env.get_state().rng == before.rng
            try:
                assert_zork_step(env.step(action), expected, final=turn == len(actions) - 1)
            except (AssertionError, ExecutionError, NotImplementedError) as error:
                error.add_note(f"Save/restore walkthrough turn {turn + 1}: {action!r}")
                raise
        assert env.done
        assert storage.saves == storage.restores == 3
    finally:
        env.close()
