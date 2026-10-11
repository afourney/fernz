"""Object snapshots compared through documented Jericho APIs, never its source."""

from copy import deepcopy

import pytest

from fernz import FernzEnv, ZObject

from .test_reference import walkthrough_trace as walkthrough_trace
from .test_reference import zork1 as zork1

pytestmark = pytest.mark.reference

# Independently measured name differences for the pinned Zork I image. Fernz
# retains the complete story text, as it already did for location queries.
NAME_DIFFERENCES = {
    1: ("pair of hands", "pair hands"),
    6: ("blast of air", "blast air"),
    15: ("Slide Room", "Slide "),
    22: ("Smelly Room", "Smelly "),
    23: ("Squeaky Room", "Squeaky "),
    25: ("Canyon View", "CanyView"),
    27: ("Canyon Bottom", "CanyBottom"),
    28: ("On the Rainbow", "On Rainbow"),
    29: ("Aragain Falls", "AragaFalls"),
    31: ("Frigid River", "River"),
    34: ("Frigid River", "River"),
    35: ("Frigid River", "River"),
    36: ("Frigid River", "River"),
    57: ("Grating Room", "Grating "),
    71: ("East of Chasm", "East Chasm"),
    80: ("South of House", "South House"),
    81: ("North of House", "North House"),
    97: ("wall with engravings", "engravings"),
    101: ("trunk of jewels", "trunk jewels"),
    102: ("The Troll Room", "Troll "),
    105: ("Torch Room", "Torch "),
    107: ("Round Room", "Round "),
    108: ("tan label", "tlabel"),
    115: ("large bag", "bag"),
    119: ("small pile of coal", "pile coal"),
    122: ("skeleton key", "skeletkey"),
    124: ("Gas Room", "Gas "),
    130: ("Frigid River", "River"),
    133: ("Dome Room", "Dome "),
    136: ("End of Rainbow", "End Rainbow"),
    137: ("pot of gold", "pot gold"),
    138: ("Loud Room", "Loud "),
    141: ("pile of plastic", "pile plastic"),
    144: ("pile of leaves", "pile leaves"),
    145: ("pile of bodies", "pile bodies"),
    146: ("small piece of vitreous slag", "piece vitreous slag"),
    147: ("pair of candles", "pair candles"),
    150: ("Mirror Room", "Mirror "),
    152: ("Mirror Room", "Mirror "),
    157: ("Machine Room", "Machine "),
    160: ("small mailbox", "mailbox"),
    163: ("large emerald", "emerald"),
    165: ("leather bag of coins", "leather bag coins"),
    166: ("burned-out lantern", "burned-lantern"),
    175: ("Egyptian Room", "Egypti"),
    180: ("West of House", "West House"),
    185: ("Cyclops Room", ""),
    187: ("Atlantis Room", "Atlant"),
    189: ("clove of garlic", "clove garlic"),
    190: ("Treasure Room", "Treasure "),
    193: ("Living Room", "Living "),
    199: ("Maintenance Room", "Maintenance "),
    200: ("group of tool chests", "group tool chests"),
    206: ("Timber Room", "Timber "),
    222: ("Bat Room", "Bat "),
    226: ("Shaft Room", "Shaft "),
    228: ("Drafty Room", "Drafty "),
    230: ("Land of the Dead", "LDead"),
    232: ("Entrance to Hades", "Entrance Hades"),
    233: ("number of ghosts", "number ghosts"),
    237: ("quantity of water", "quantity water"),
    240: ("mountain range", "mountarange"),
    248: ("set of teeth", "set teeth"),
}
UNNAMED_OBJECTS = {82, 247, 249}
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
