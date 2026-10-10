"""Black-box API comparisons: never inspect Jericho or Frotz implementation code."""

import hashlib

import pytest

from fernz import ExecutionError, FernzEnv

pytestmark = pytest.mark.reference

ZORK1_SHA256 = "0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd"
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
                    observation, reward, done, info = env.step(action)
                    assert type(reward) is int
                    assert reward == expected[1]
                    assert type(done) is bool
                    assert done == expected[2]
                    if turn < len(actions):
                        assert_zork_turn(observation, expected[0])
                        assert_info(info, expected[3])
                    else:
                        # This ending executes quit. Black-box Jericho adds one
                        # final newline and reports 395 moves; the story prints
                        # 394. Fernz stops at quit and returns the status global
                        # (394), consistent with the standalone Frotz ending.
                        # Assert these exact differences only on the final turn.
                        assert observation.startswith("\n")
                        assert observation.endswith("\n")
                        assert expected[0].endswith("\n\n")
                        assert_observation(observation.removeprefix("\n") + "\n", expected[0])
                        assert_info(info, {"score": 350, "moves": 394})
                        assert_info(expected[3], {"score": 350, "moves": 395})
                        assert env.done is True
                except (AssertionError, ExecutionError, NotImplementedError) as error:
                    error.add_note(f"Walkthrough episode {episode}, turn {turn}: {action!r}")
                    raise
    finally:
        env.close()
