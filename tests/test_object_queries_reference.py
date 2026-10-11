"""Object snapshots compared through documented Jericho APIs, never its source."""

from copy import deepcopy

import pytest

from fernz import FernzEnv, ZObject

from .test_reference import walkthrough_trace as walkthrough_trace
from .test_reference import zork1 as zork1
from .zork_compat import NAME_DIFFERENCES, UNNAMED_OBJECTS

pytestmark = pytest.mark.reference

# At the third canyon death, the interpreters halt with different thief
# positions. Compare every other field and pin these exact raw-state differences;
# do not normalize all thief movement away in a raw inspection test.
TERMINAL_DEATH_LINKS = {
    (52, "child"): (0, 114),
    (114, "parent"): (185, 52),
    (114, "sibling"): (186, 0),
    (185, "child"): (114, 186),
}


def assert_object(actual, expected, *, terminal_death=False):
    assert isinstance(actual, ZObject)
    for field in ("num", "parent", "sibling", "child"):
        pair = getattr(actual, field), getattr(expected, field)
        key = actual.num, field
        if terminal_death and key in TERMINAL_DEATH_LINKS:
            assert pair == TERMINAL_DEATH_LINKS[key]
        else:
            assert pair[0] == pair[1], key
    assert actual.attr == list(expected.attr), actual.num
    assert actual.properties == list(expected.properties), actual.num
    if actual.num in NAME_DIFFERENCES:
        assert (actual.name, expected.name) == NAME_DIFFERENCES[actual.num]
    else:
        assert actual.name == expected.name, actual.num


def assert_inspection(env, reference, *, direct=False, terminal_death=False):
    before, native_before = env.get_state(), reference.get_state()
    world, native_world = env.get_world_objects(), reference.get_world_objects(clean=False)
    assert len(world) == len(native_world) == 251
    for number, (actual, expected) in enumerate(zip(world, native_world, strict=True)):
        assert actual.num == number
        if number in UNNAMED_OBJECTS:
            # The reference omits these real nodes despite incoming links.
            # Keep them traversable rather than silently discarding their data.
            assert actual.name == ""
            assert expected.num == expected.parent == expected.sibling == expected.child == 0
            assert expected.name == ""
            assert list(expected.attr) == [0] * 32
            assert list(expected.properties) == [0] * 16
            if direct:
                assert reference.get_object(number) is None
        else:
            assert_object(actual, expected, terminal_death=terminal_death)
            if direct and number:
                assert_object(
                    env.get_object(number),
                    reference.get_object(number),
                    terminal_death=terminal_death,
                )
        if direct:
            assert env.get_object(number) == (actual if number else None)
    assert_object(env.get_player_object(), reference.get_player_object())
    assert_object(env.get_player_location(), reference.get_player_location())
    inventory, native_inventory = env.get_inventory(), reference.get_inventory()
    assert len(inventory) == len(native_inventory)
    for actual, expected in zip(inventory, native_inventory, strict=True):
        assert_object(actual, expected)
    assert env.get_state() == before
    native_after = reference.get_state()
    assert [a.tobytes() for a in native_before[:2]] == [a.tobytes() for a in native_after[:2]]
    assert native_before[2:] == native_after[2:]


def test_object_queries_at_every_winning_walkthrough_boundary(zork1, walkthrough_trace):
    from jericho import FrotzEnv

    seed, actions, _, _ = walkthrough_trace
    env, reference = FernzEnv(zork1, seed=seed), FrotzEnv(str(zork1), seed=seed)
    try:
        env.reset()
        reference.reset()
        initial, native_initial = env.get_state(), reference.get_state()
        assert_inspection(env, reference, direct=True)
        for turn, action in enumerate(actions, 1):
            env.step(action)
            reference.step(action)
            assert_inspection(env, reference)
            if turn in (35, 218, 387, 396):
                # Include inventory containers, a vehicle, and the halted ending.
                saved, native_saved = env.get_state(), reference.get_state()
                fork = env.copy()
                try:
                    assert_inspection(fork, reference, direct=True)
                finally:
                    fork.close()
                env.set_state(initial)
                reference.set_state(native_initial)
                assert_inspection(env, reference)
                env.set_state(saved)
                reference.set_state(native_saved)
                assert_inspection(env, reference)
        assert env.done and reference.victory()
    finally:
        env.close()
        reference.close()


def test_returned_records_are_independent_and_survive_gameplay(zork1):
    from jericho import FrotzEnv

    for env in (FernzEnv(zork1, seed=12), FrotzEnv(str(zork1), seed=12)):
        try:
            env.reset()
            player = env.get_player_object()
            second = env.get_object(player.num)
            world_player = env.get_world_objects()[player.num]
            saved = deepcopy(player)
            second.parent = 0
            second.properties[0] = 1
            assert player.parent == world_player.parent == env.get_player_object().parent == 180
            assert list(player.properties) == list(world_player.properties)
            assert list(env.get_object(player.num).properties) == list(player.properties)
            env.step("north")
            assert player.parent == world_player.parent == saved.parent == 180
            assert env.get_player_object().parent == 81
            env.reset()
            mailbox = env.get_object(160)
            old_attributes = list(mailbox.attr)
            env.step("open mailbox")
            assert list(mailbox.attr) == old_attributes
            assert list(env.get_object(160).attr) != old_attributes
            env.step("take leaflet")
            inventory = env.get_inventory()
            assert [obj.num for obj in inventory] == [161]
            assert inventory[0].parent == 4
            env.step("drop leaflet")
            assert env.get_inventory() == []
            assert inventory[0].parent == 4
            assert env.get_object(161).parent == 180
            for number in (-1, 0, 251, 255, 256):
                assert env.get_object(number) is None
        finally:
            env.close()


def test_object_queries_through_recoverable_and_terminal_death(zork1):
    from jericho import FrotzEnv

    env, reference = FernzEnv(zork1, seed=12), FrotzEnv(str(zork1), seed=12)
    try:
        env.reset()
        reference.reset()
        actions = ["south", "east", "east", "east", "jump"]
        actions += ["east", "south", "east", "east", "east", "jump"] * 2
        for action in actions:
            env.step(action)
            reference.step(action)
            assert_inspection(env, reference, terminal_death=env.done)
        assert env.done and env.game_over()
    finally:
        env.close()
        reference.close()
