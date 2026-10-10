"""Black-box API comparisons: never inspect Jericho or Frotz implementation code."""

import hashlib

import pytest

from fernz import FernzEnv

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

    env = FrotzEnv(str(zork1), seed=0)
    try:
        initial = env.reset()
        steps = [env.step(action) for action in ACTIONS]
        assert env.reset() == initial, "Jericho reset did not restore the opening"
        assert [env.step(action) for action in ACTIONS] == steps, "Unstable reference trace"
        return initial, steps
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
    env = FernzEnv(zork1)
    try:
        for _ in range(2):
            observation, info = env.reset()
            assert_zork_opening(observation, expected[0])
            assert_info(info, expected[1])
            env.memory.write_word(env.story.header.globals_table + 2, 0xFFFF)
    finally:
        env.close()


@pytest.mark.xfail(
    raises=NotImplementedError,
    strict=True,
    reason="Command input and tokenization are not implemented; remove once the sequence matches",
)
def test_zork1_short_sequence_matches_jericho(zork1, reference_trace):
    initial, expected_steps = reference_trace
    env = FernzEnv(zork1)
    try:
        # Compare two episodes to exercise reset after play as well as fresh reset.
        for _ in range(2):
            observation, info = env.reset()
            assert_zork_opening(observation, initial[0])
            assert_info(info, initial[1])
            for action, expected in zip(ACTIONS, expected_steps, strict=True):
                observation, reward, done, info = env.step(action)
                assert_observation(observation, expected[0])
                assert type(reward) is int
                assert reward == expected[1], action
                assert type(done) is bool
                assert done == expected[2], action
                assert_info(info, expected[3])
    finally:
        env.close()
