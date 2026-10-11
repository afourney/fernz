"""Zork I detours compared using public Jericho calls, never reference source."""

from dataclasses import fields

import pytest

from fernz import FernzEnv

from .state_bridge import StateBridge
from .test_reference import assert_info, assert_zork_opening, assert_zork_turn
from .test_reference import zork1 as zork1
from .zork_scenarios import (
    CELLAR_DEATH_ACTIONS,
    CHECKPOINTS,
    COMBAT_ACTIONS,
    COMBAT_SEEDS,
    COMMAND_GROUPS,
    SCENARIOS,
)

pytestmark = pytest.mark.reference

COMMANDS = [
    pytest.param(command, id=f"{group}:{command or '<empty>'}")
    for group, commands in COMMAND_GROUPS.items()
    for command in commands
]


def assert_state(env, reference, bridge):
    """Compare all snapshot fields, with useful diagnostics for large RAM blobs."""
    actual, expected = env.get_state(), bridge.from_jericho(reference.get_state())
    for field in fields(actual):
        left, right = getattr(actual, field.name), getattr(expected, field.name)
        if field.name == "ram":
            assert len(left) == len(right)
            differences = [
                (hex(i), a, b) for i, (a, b) in enumerate(zip(left, right, strict=True)) if a != b
            ]
            assert not differences, f"RAM differences (address, Fernz, Jericho): {differences[:20]}"
        else:
            assert left == right, field.name


def compare_turn(env, reference, bridge, action):
    actual, expected = env.step(action), reference.step(action)
    assert_zork_turn(actual[0], expected[0])
    assert type(actual[1]) is int and actual[1] == expected[1]
    assert_info(actual[3], expected[3])
    # These detours remain playable, including a recoverable death. Jericho's
    # done reports a response outcome; Fernz's done means the VM executed quit.
    assert actual[2] is False
    assert expected[2] is (reference.game_over() or reference.victory())
    assert env.game_over() is reference.game_over()
    assert env.victory() is reference.victory()
    assert env.get_player_location().num == reference.get_player_location().num
    assert env.get_score() == reference.get_score()
    assert env.get_moves() == reference.get_moves()
    assert_state(env, reference, bridge)
    return actual, expected


@pytest.fixture(scope="module")
def checkpoint_envs(zork1):
    from jericho import FrotzEnv

    reference = FrotzEnv(str(zork1))
    seed = reference.seed()
    assert seed == 12
    actions = reference.get_walkthrough()
    assert len(actions) == 396
    env = FernzEnv(zork1, seed=seed)
    try:
        initial, native_initial = env.reset(), reference.reset()
        assert_zork_opening(initial[0], native_initial[0])
        assert_info(initial[1], native_initial[1])
        bridge = StateBridge(env.story, reference.get_state(), seed=seed)
        assert_state(env, reference, bridge)
        checkpoints = {}
        by_turn = {turn: (name, room) for name, (turn, room) in CHECKPOINTS.items()}
        for turn in range(max(by_turn) + 1):
            if turn:
                try:
                    compare_turn(env, reference, bridge, actions[turn - 1])
                except (AssertionError, RuntimeError, ValueError) as error:
                    error.add_note(
                        f"Building checkpoint, walkthrough turn {turn}: {actions[turn - 1]!r}"
                    )
                    raise
            if turn in by_turn:
                name, room = by_turn[turn]
                assert env.get_player_location().num == room
                checkpoints[name] = env.get_state(), reference.get_state()
        yield env, reference, bridge, checkpoints
    finally:
        env.close()
        reference.close()


@pytest.mark.parametrize("checkpoint", CHECKPOINTS)
@pytest.mark.parametrize("action", COMMANDS)
def test_off_path_command_and_followups(checkpoint_envs, checkpoint, action):
    env, reference, bridge, checkpoints = checkpoint_envs
    state, native_state = checkpoints[checkpoint]
    env.set_state(state)
    reference.set_state(native_state)
    for turn, command in enumerate((action, "look", "inventory"), 1):
        try:
            compare_turn(env, reference, bridge, command)
        except (AssertionError, RuntimeError, ValueError) as error:
            error.add_note(
                f"Checkpoint {checkpoint}, seed 12, detour {action!r}, turn {turn}: {command!r}"
            )
            raise


# Each scenario starts independently, then keeps parser and game side effects
# across turns. Replay the whole branch to check snapshots, RNG, and follow-ups.


@pytest.mark.parametrize(
    "checkpoint,actions", [pytest.param(s.checkpoint, s.actions, id=s.id) for s in SCENARIOS]
)
def test_multi_turn_detour_replays_exactly(checkpoint_envs, checkpoint, actions):
    env, reference, bridge, checkpoints = checkpoint_envs
    state, native_state = checkpoints[checkpoint]
    first_trace = None
    first_state = None
    for replay in range(2):
        env.set_state(state)
        reference.set_state(native_state)
        trace = []
        for turn, action in enumerate(actions, 1):
            try:
                trace.append(compare_turn(env, reference, bridge, action))
            except (AssertionError, RuntimeError, ValueError) as error:
                error.add_note(
                    f"Checkpoint {checkpoint}, seed 12, replay {replay}, turn {turn}: {action!r}"
                )
                raise
        if replay == 0:
            first_trace, first_state = trace, env.get_state()
        else:
            assert trace == first_trace
            assert env.get_state() == first_state


def test_cellar_chasm_death_replays_and_allows_continued_play(checkpoint_envs):
    env, reference, bridge, checkpoints = checkpoint_envs
    state, native_state = checkpoints["living-room"]
    env.set_state(state)
    reference.set_state(native_state)
    for action in CELLAR_DEATH_ACTIONS[:5]:
        compare_turn(env, reference, bridge, action)
        assert not env.game_over()
    assert env.get_player_location().name == "Cellar"
    compare_turn(env, reference, bridge, "south")
    assert env.get_player_location().name == "East of Chasm"
    assert not env.game_over()
    ledge, native_ledge = env.get_state(), reference.get_state()
    score_before = env.get_score()

    first_result = None
    first_state = None
    for replay in range(2):
        env.set_state(ledge)
        reference.set_state(native_ledge)
        result = compare_turn(env, reference, bridge, "jump")
        actual, expected = result
        assert "You have died" in actual[0]
        assert actual[1] == expected[1] == -10
        assert env.get_score() == score_before - 10
        assert env.game_over() is reference.game_over() is True
        assert not env.done  # The first death respawns the player.
        assert env.get_player_location().name == "Forest"
        if replay == 0:
            first_result, first_state = result, env.get_state()
        else:
            assert result == first_result
            assert env.get_state() == first_state
        for action in ("look", "inventory", "wait"):
            compare_turn(env, reference, bridge, action)
            assert env.game_over() is reference.game_over() is False


@pytest.mark.parametrize("seed", COMBAT_SEEDS)
def test_combat_detour_with_different_seeds(zork1, seed):
    from jericho import FrotzEnv

    env, reference = FernzEnv(zork1, seed=seed), FrotzEnv(str(zork1), seed=seed)
    actions = COMBAT_ACTIONS
    try:
        first_trace = None
        first_state = None
        for episode in range(2):
            initial, native_initial = env.reset(), reference.reset()
            assert_zork_opening(initial[0], native_initial[0])
            assert_info(initial[1], native_initial[1])
            bridge = StateBridge(env.story, reference.get_state(), seed=seed)
            opening_rng = env.get_state().rng
            trace = []
            for turn, action in enumerate(actions, 1):
                try:
                    trace.append(compare_turn(env, reference, bridge, action))
                except (AssertionError, RuntimeError, ValueError) as error:
                    error.add_note(
                        f"Combat seed {seed}, episode {episode}, turn {turn}: {action!r}"
                    )
                    raise
            assert "troll" in trace[12][0][0].lower()
            assert env.get_state().rng != opening_rng
            if episode == 0:
                first_trace, first_state = trace, env.get_state()
            else:
                assert trace == first_trace
                assert env.get_state() == first_state
    finally:
        env.close()
        reference.close()


@pytest.mark.parametrize("action", ("?", "look?", "?look", "look ?", "? ?", "take ?"))
def test_question_marks_are_an_explicit_reference_input_difference(checkpoint_envs, action):
    env, reference, bridge, checkpoints = checkpoint_envs
    state, native_state = checkpoints["west-house"]
    env.set_state(state)
    reference.set_state(native_state)
    actual, expected = env.step(action), reference.step(action)
    text = state.input_request.text + 1
    size = len(action) + 1
    # Public RAM snapshots show the reference substituting spaces for '?' in
    # this ROM. Standard §13's remarks explicitly reject this substitution.
    # Fernz preserves printable ZSCII; don't hide the difference
    # by filtering punctuation in ordinary command comparisons.
    assert env.get_state().ram[text : text + size] == action.encode() + b"\0"
    native_after = reference.get_state()
    substituted = action.replace("?", " ")
    assert native_after[0][text : text + size].tobytes() == substituted.encode() + b"\0"
    assert "I don't know the word" in actual[0]
    assert actual[0].removeprefix("\n").removesuffix(">") != expected[0]
    env.set_state(state)
    equivalent = env.step(substituted)
    assert_zork_turn(equivalent[0], expected[0])
    assert equivalent[1:] == expected[1:]
    assert_state(env, reference, bridge)


@pytest.mark.parametrize("length", (98, 99, 100, 150, 197, 198, 199, 250))
def test_long_command_limits_are_an_explicit_reference_difference(checkpoint_envs, length):
    env, reference, bridge, checkpoints = checkpoint_envs
    state, native_state = checkpoints["west-house"]
    env.set_state(state)
    reference.set_state(native_state)
    action = "take " + "x" * (length - 5)
    text = state.input_request.text
    assert state.ram[text] == 100
    actual = env.step(action)
    if length > 198:
        with pytest.warns(UserWarning, match="actions should have less than 198 characters"):
            expected = reference.step(action)
    else:
        expected = reference.step(action)
    accepted, native_accepted = action[:99], action[:198]
    # V3 read reserves the final byte for NUL (§15 read). The reference's public
    # input path accepts more than the declared capacity of this story buffer.
    assert env.get_state().ram[text + 1 : text + 101] == accepted.encode() + b"\0" * (
        100 - len(accepted)
    )
    assert (
        reference.get_state()[0][text + 1 : text + 2 + len(native_accepted)].tobytes()
        == native_accepted.encode() + b"\0"
    )
    if length <= 99:
        assert_zork_turn(actual[0], expected[0])
        assert actual[1:] == expected[1:]
        assert_state(env, reference, bridge)
    else:
        assert actual[0].removeprefix("\n").removesuffix(">") != expected[0]
        reference.set_state(native_state)
        bounded = reference.step(accepted)
        assert_zork_turn(actual[0], bounded[0])
        assert actual[1:] == bounded[1:]
        assert_state(env, reference, bridge)
