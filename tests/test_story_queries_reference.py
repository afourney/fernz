"""Story queries measured solely through public Jericho calls and game output."""

import pytest

from fernz import FernzEnv, Location

from .test_reference import assert_observation, assert_zork_step, assert_zork_turn
from .test_reference import walkthrough_trace as walkthrough_trace
from .test_reference import zork1 as zork1
from .test_save_restore import Storage

pytestmark = pytest.mark.reference

# Full story short names versus names returned by the pinned public reference.
# Keep these differences explicit; do not remove words from runtime names.
ROOM_NAMES = {
    180: ("West of House", "West House"),
    81: ("North of House", "North House"),
    193: ("Living Room", "Living "),
    25: ("Canyon View", "CanyView"),
    178: ("Stone Barrow", "Stone Barrow"),
    156: ("magic boat", "magic boat"),
}


def assert_queries(env, reference):
    before, native_before = env.get_state(), reference.get_state()
    room, native_room = env.get_player_location(), reference.get_player_location()
    assert isinstance(room, Location)
    assert room.num == native_room.num
    if room.num in ROOM_NAMES:
        assert (room.name, native_room.name) == ROOM_NAMES[room.num]
    assert env.get_max_score() == reference.get_max_score() == 350
    assert env.game_over() is reference.game_over()
    assert env.victory() is reference.victory()
    assert env.get_state() == before
    native_after = reference.get_state()
    assert [a.tobytes() for a in native_before[:2]] == [a.tobytes() for a in native_after[:2]]
    assert native_before[2:] == native_after[2:]


def test_queries_through_winning_walkthrough_and_snapshot_restore(zork1, walkthrough_trace):
    from jericho import FrotzEnv

    seed, actions, _, steps = walkthrough_trace
    env, reference = FernzEnv(zork1, seed=seed), FrotzEnv(str(zork1), seed=seed)
    try:
        assert env.get_max_score() == 350
        env.reset()
        reference.reset()
        initial, native_initial = env.get_state(), reference.get_state()
        assert_queries(env, reference)
        for turn, (action, expected) in enumerate(zip(actions, steps, strict=True), 1):
            assert reference.step(action) == expected
            assert_zork_step(env.step(action), expected, final=turn == len(actions))
            assert_queries(env, reference)
            assert not env.game_over()
            assert env.victory() is (turn == len(actions))
            if turn == 387:
                assert env.get_score() == 350 and not env.victory()
            if turn == 218:
                assert env.get_player_location() == Location(156, "magic boat")
                assert env.memory.read_word(env.story.header.globals_table) == 33
            if turn in (35, 387, 395, 396):
                saved, native_saved = env.get_state(), reference.get_state()
                fork = env.copy()
                assert fork.get_state() == saved
                assert_queries(fork, reference)
                fork.close()
                env.set_state(initial)
                reference.set_state(native_initial)
                assert not env.victory() and not env.game_over()
                env.set_state(saved)
                reference.set_state(native_saved)
                assert_queries(env, reference)
        assert env.done and env.victory()
        won = env.get_state()
        native_won = reference.get_state()
        # As with death, the reference's victory query follows its narrative.
        reference.set_state((*native_won[:8], b"Observation not available"))
        assert not reference.victory()
        reference.set_state((*native_initial[:8], native_won[8]))
        assert reference.victory()
        env.reset()
        reference.reset()
        assert_queries(env, reference)
        env.set_state(won)
        assert env.victory() and not env.game_over()
    finally:
        env.close()
        reference.close()


def test_recoverable_and_terminal_deaths_with_copies_and_checkpoints(zork1):
    from jericho import FrotzEnv

    env, reference = FernzEnv(zork1, seed=12), FrotzEnv(str(zork1), seed=12)
    try:
        env.reset()
        reference.reset()
        # Two recoverable canyon falls, then the third death ends the story.
        actions = ["south", "east", "east", "east", "jump"]
        actions += ["east", "south", "east", "east", "east", "jump"] * 2
        for turn, action in enumerate(actions, 1):
            before, native_before = env.get_state(), reference.get_state()
            actual, expected = env.step(action), reference.step(action)
            assert_queries(env, reference)
            assert env.game_over() is (action == "jump")
            assert not env.victory()
            if turn < len(actions):
                assert_zork_turn(actual[0], expected[0])
                assert actual[1] == expected[1]
                assert actual[3] == expected[3]
                assert actual[2] is False  # Fernz permits play after recoverable death.
                assert expected[2] is (action == "jump")
            else:
                assert actual[2] is expected[2] is True
                assert actual[1] == expected[1] == -10
                assert actual[3] == {"score": -30, "moves": 16}
                assert expected[3] == {"score": -30, "moves": 17}
                assert actual[0].startswith("\n") and expected[0].endswith("\n\n")
                assert_observation(actual[0].removeprefix("\n") + "\n", expected[0])
            if action == "jump":
                saved, native_saved = env.get_state(), reference.get_state()
                fork = env.copy()
                assert_queries(fork, reference)
                fork.close()
                env.set_state(before)
                reference.set_state(native_before)
                assert_queries(env, reference)
                assert not env.game_over()
                assert env.step(action) == actual
                assert reference.step(action) == expected
                # Restore the post-death flags without executing a turn.
                env.set_state(saved)
                reference.set_state(native_saved)
                assert_queries(env, reference)
        assert env.done and env.game_over()
    finally:
        env.close()
        reference.close()


def test_death_query_uses_the_public_narrative_not_just_ram(zork1):
    from jericho import FrotzEnv

    from .state_bridge import StateBridge

    reference = FrotzEnv(str(zork1), seed=12)
    env = FernzEnv(zork1, seed=12)
    try:
        reference.reset()
        initial = reference.get_state()
        bridge = StateBridge(env.story, initial, seed=12)
        for action in ("south", "east", "east", "east", "jump"):
            reference.step(action)
        dead = reference.get_state()
        assert reference.game_over()
        env.set_state(bridge.from_jericho(dead))
        assert_queries(env, reference)
        reference.set_state((*dead[:8], b"Observation not available"))
        assert not reference.game_over()
        reference.set_state((*initial[:8], dead[8]))
        assert reference.game_over() and not reference.victory()
        reference.set_state(dead)
        reference.step("look")
        env.step("look")
        assert_queries(env, reference)
        assert not reference.game_over()
    finally:
        reference.close()
        env.close()


def test_queries_after_story_save_restore_restart_and_voluntary_quit(zork1, tmp_path, monkeypatch):
    from jericho import FrotzEnv

    monkeypatch.chdir(tmp_path)
    storage = Storage()
    env = FernzEnv(zork1, seed=12, save_handler=storage.save, restore_handler=storage.restore)
    reference = FrotzEnv(str(zork1), seed=12)
    try:
        env.reset()
        reference.reset()
        for action in ("north", "save", "east", "restart", "yes", "restore", "quit", "yes"):
            env.step(action)
            reference.step(action)
            assert_queries(env, reference)
            assert not env.game_over() and not env.victory()
        assert env.done  # Voluntary quit is neither a loss nor a victory.
        env.reset()
        reference.reset()
        assert_queries(env, reference)
    finally:
        env.close()
        reference.close()
