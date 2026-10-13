"""Detached object inspection of independent stories and malformed tables."""

from dataclasses import replace
from hashlib import sha256

import pytest

from fernz import ExecutionError, FernzEnv, Memory, Story, ZObject, _profiles
from fernz._objects import Objects
from fernz._profiles import StoryProfile

from .story_files import READ, program_bytes, put_word, zchars


def object_story():
    data = bytearray(program_bytes(READ + b"\xb4" + READ + b"\xba"))
    # Five contiguous entries followed immediately by their property tables.
    # room -> player -> bag -> coin; lamp is the bag's sibling in inventory.
    cursor = 0x7E + 5 * 9
    links = [(0, 0, 2), (1, 0, 3), (2, 5, 4), (3, 0, 0), (2, 0, 0)]
    names = [(23, 20, 20, 18), (30, 20, 26), (7, 6, 12), (10, 12, 12), (7, 20, 29)]
    for number, ((parent, sibling, child), chars) in enumerate(zip(links, names, strict=True), 1):
        entry = 0x7E + 9 * (number - 1)
        data[entry : entry + 4] = b"\x80\x00\x00\x01"
        data[entry + 4 : entry + 7] = bytes((parent, sibling, child))
        put_word(data, entry + 7, cursor)
        text = zchars(*chars)
        properties = bytes.fromhex("2a 12 34 07 56 01 78 00") if number == 3 else b"\x00"
        table = bytes((len(text) // 2,)) + text + properties
        data[cursor : cursor + len(table)] = table
        cursor += len(table)
    assert cursor < 0x100
    put_word(data, 0x100, 1)
    put_word(data, 0x1C, sum(data[64:]) & 0xFFFF)
    return bytes(data)


@pytest.fixture
def object_env(tmp_path, monkeypatch):
    data = object_story()
    path = tmp_path / "objects.z3"
    path.write_bytes(data)
    profile = StoryProfile(10, frozenset(), frozenset(), player_object=2)
    monkeypatch.setitem(_profiles._PROFILES, sha256(data).hexdigest(), profile)
    env = FernzEnv(path, seed=12)
    env.reset()
    return env


def test_world_slots_fields_and_traversal_from_a_direct_lookup(object_env):
    env = object_env
    before = env.get_state()
    world = env.get_world_objects()
    assert [obj.num for obj in world] == [0, 1, 2, 3, 4, 5]
    assert world[0] == ZObject(0, "")
    assert [obj.name for obj in world] == ["", "room", "you", "bag", "egg", "box"]
    assert world[3].attr == [1] + [0] * 30 + [1]
    assert world[3].properties == [10, 7, 1] + [0] * 13
    assert env.get_object(0) is None
    for number in range(1, len(world)):
        assert env.get_object(number) == world[number]
        assert env.get_object(number) is not world[number]
    player = env.get_player_object()
    assert player == env.get_object(2)
    assert env.get_player_location() == env.get_object(player.parent) == world[1]
    bag = env.get_object(player.child)
    assert bag == world[3]
    assert env.get_object(bag.sibling) == world[5]
    assert env.get_object(bag.child) == world[4]
    assert [obj.num for obj in env.get_inventory()] == [3, 5]
    assert env.get_state() == before


def test_results_and_nested_lists_are_mutable_but_detached(object_env):
    env = object_env
    before = env.get_state()
    world = env.get_world_objects()
    player = env.get_player_object()
    inventory = env.get_inventory()
    bag = env.get_object(3)
    room = env.get_player_location()
    bag.parent = 0
    bag.attr[0] = 0
    bag.properties[0] = 2
    player.name = "edited"
    room.child = 0
    world[0].attr[0] = 1
    assert world[3].parent == inventory[0].parent == 2
    assert world[3].attr[0] == inventory[0].attr[0] == 1
    assert world[3].properties[0] == inventory[0].properties[0] == 10
    assert env.get_object(3) == world[3]
    assert env.get_player_object().name == "you"
    assert env.get_player_location().child == 2
    assert env.get_world_objects()[0] == ZObject(0, "")
    assert env.get_state() == before


def test_saved_objects_survive_movement_restore_reset_and_copy(object_env):
    env = object_env
    saved = env.get_state()
    bag = env.get_object(3)
    inventory = env.get_inventory()
    fork = env.copy()
    Objects(env.memory).insert(3, 1)
    assert env.get_object(3).parent == 1
    assert [obj.num for obj in env.get_inventory()] == [5]
    assert bag.parent == inventory[0].parent == fork.get_object(3).parent == 2
    env.set_state(saved)
    assert env.get_object(3) == bag
    env.reset()
    assert env.get_object(3) == bag
    assert fork.get_state() == saved


@pytest.mark.parametrize("number", [-1000, -1, 0, 6, 255, 256, 65536])
def test_missing_objects_return_none(object_env, number):
    assert object_env.get_object(number) is None


@pytest.mark.parametrize("number", [1.5, "2", None])
def test_non_integer_object_numbers_fail(object_env, number):
    with pytest.raises(TypeError):
        object_env.get_object(number)


def test_integer_protocol_and_boolean_object_numbers(object_env):
    class Number:
        def __index__(self):
            return 2

    assert object_env.get_object(Number()) == object_env.get_object(2)
    assert object_env.get_object(True) == object_env.get_object(1)


def test_count_uses_initial_table_and_allows_relocated_property_tables(object_env):
    env = object_env
    # Move the earliest table before the first public enumeration. Counting
    # current pointers would incorrectly shrink or enlarge the object table.
    env.memory.write_bytes(0x220, b"\x01" + zchars(29, 30, 31) + b"\x00")
    env.memory.write_word(0x85, 0x220)
    assert len(env.get_world_objects()) == 6
    assert env.get_object(1).name == "xyz"
    restored = FernzEnv(env.game_path)
    restored.set_state(env.get_state())
    assert restored.get_world_objects() == env.get_world_objects()


def test_count_finds_the_earliest_table_even_when_properties_are_out_of_order():
    data = bytearray(object_story())
    first, last = 0x85, 0x85 + 4 * 9
    data[first : first + 2], data[last : last + 2] = data[last : last + 2], data[first : first + 2]
    assert Objects(Memory(Story(data))).count == 5


@pytest.mark.parametrize("pointer", [0, 0x40, 0xAC, 0x300, 0xFFFF])
def test_enumeration_rejects_ambiguous_initial_layouts(tmp_path, pointer):
    data = bytearray(object_story())
    put_word(data, 0x85, pointer)
    path = tmp_path / "ambiguous.z3"
    path.write_bytes(data)
    env = FernzEnv(path)
    env.reset()
    before = env.get_state()
    for query in (env.get_world_objects, lambda: env.get_object(1)):
        with pytest.raises(NotImplementedError, match="infer object count"):
            query()
    # Object 256 cannot exist in V3, so no count inference is needed.
    assert env.get_object(256) is None
    assert env.get_state() == before


def test_maximum_v3_object_count_and_noncontiguous_layout():
    data = bytearray(program_bytes(b"\xba"))
    end = 0x7E + 255 * 9
    put_word(data, 0x0E, end + 2)
    for number in range(255):
        put_word(data, 0x85 + 9 * number, end)
    assert Objects(Memory(Story(data))).count == 255
    # Moving the property table leaves a padding byte between it and the entries.
    for number in range(255):
        put_word(data, 0x85 + 9 * number, end + 1)
    with pytest.raises(NotImplementedError, match="infer object count"):
        _ = Objects(Memory(Story(data))).count


def test_disconnected_and_unnamed_objects_are_preserved(object_env):
    env = object_env
    Objects(env.memory).remove(3)
    env.memory.write_bytes(0x220, b"\x00\x00")
    env.memory.write_word(0x7E + 9 * 2 + 7, 0x220)
    world = env.get_world_objects()
    assert world[3].num == 3 and world[3].name == "" and world[3].parent == 0
    assert world[3].child == 4
    assert env.get_object(3) == world[3]


def test_more_than_sixteen_properties_are_not_discarded(object_env):
    env = object_env
    properties = b"".join(bytes((n, n)) for n in range(31, 0, -1))
    env.memory.write_bytes(0x220, b"\x00" + properties + b"\x00")
    env.memory.write_word(0x85, 0x220)
    assert env.get_object(1).properties == list(range(31, 0, -1))


@pytest.mark.parametrize("mutation", ["cycle", "parent", "property", "name"])
def test_malformed_data_fails_without_altering_state(object_env, mutation):
    env = object_env
    if mutation == "cycle":
        env.memory.write_byte(0x7E + 9 * 4 + 5, 3)
        query, error = env.get_inventory, "sibling chain"
    elif mutation == "parent":
        env.memory.write_byte(0x7E + 9 * 2 + 4, 1)
        query, error = env.get_inventory, "parent link"
    elif mutation == "property":
        env.memory.write_word(0x85, 0x220)
        env.memory.write_bytes(0x220, b"\x00\x01\x00\x02\x00\x00")
        query, error = env.get_world_objects, "property order"
    else:
        env.memory.write_word(0x85, 0x2FF)
        env.memory.write_byte(0x2FF, 1)
        query, error = env.get_world_objects, "outside dynamic"
    before = env.get_state()
    with pytest.raises(ExecutionError, match=error):
        query()
    assert env.get_state() == before


def test_queries_require_initialization_recover_after_failure_and_work_after_quit(object_env):
    env = FernzEnv(object_env.game_path)
    queries = [
        lambda: env.get_object(1),
        env.get_world_objects,
        env.get_player_object,
        env.get_player_location,
        env.get_inventory,
    ]
    for query in queries:
        with pytest.raises(RuntimeError, match="reset"):
            query()
    env.reset()
    saved = env.get_state()
    with pytest.raises(ExecutionError, match="budget"):
        env.step("look", max_steps=1)
    for query in queries:
        with pytest.raises(RuntimeError, match="reset"):
            query()
    env.set_state(saved)
    env.step("look")
    env.step("look")
    assert env.done
    assert [obj.num for obj in env.get_inventory()] == [3, 5]
    assert env.get_object(1) == env.get_player_location()


def test_player_queries_require_known_player_but_raw_inspection_does_not(object_env, monkeypatch):
    digest = sha256(object_env.story.data).hexdigest()
    for profile in (None, replace(object_env._profile, player_object=None)):
        if profile is None:
            monkeypatch.delitem(_profiles._PROFILES, digest)
        else:
            monkeypatch.setitem(_profiles._PROFILES, digest, profile)
        env = FernzEnv(object_env.game_path)
        env.reset()
        assert len(env.get_world_objects()) == 6
        assert env.get_player_location() == env.get_object(1)
        for query in (env.get_player_object, env.get_inventory):
            with pytest.raises(NotImplementedError, match="profile"):
                query()


def test_cleaning_is_explicitly_deferred(object_env):
    before = object_env.get_state()
    with pytest.raises(NotImplementedError, match="Cleaned"):
        object_env.get_world_objects(clean=True)
    assert object_env.get_state() == before


def test_queries_do_not_call_host_callbacks_or_change_state(object_env, capsys):
    def forbidden(*args):
        pytest.fail("Inspection must not call the host")

    env = FernzEnv(
        object_env.game_path,
        save_handler=forbidden,
        restore_handler=forbidden,
    )
    before = object_env.get_state()
    env.set_state(before)
    env.get_object(1)
    env.get_world_objects()
    env.get_player_object()
    env.get_player_location()
    env.get_inventory()
    assert env.get_state() == before
    assert capsys.readouterr() == ("", "")
