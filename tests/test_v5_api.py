"""Independent V5 API contracts, detached objects, and snapshot lifecycle."""

from dataclasses import FrozenInstanceError, replace
from hashlib import sha256

import pytest

from fernz import ExecutionError, FernzEnv, GameState, _profiles
from fernz._objects import Objects
from fernz._profiles import StoryProfile

from .story_files import put_word
from .test_story_queries import printed
from .test_v5_foundations import object_memory


@pytest.fixture
def object_env(tmp_path, monkeypatch):
    memory = object_memory()
    objects = Objects(memory)
    objects.insert(299, 1)
    objects.insert(300, 299)
    objects.insert(298, 299)
    objects.insert(297, 300)
    objects.attribute(300, 47, True)
    objects.attribute(299, 32, True)
    data = bytearray(memory.read_bytes(0, len(memory)))
    # Text and parse buffers live beyond the 300-object table; global 17 is
    # an elapsed-time counter for this independent test profile.
    data[0x1600] = 40
    data[0x1640] = 6
    put_word(data, 0x1800 + 34, 545)
    read = bytes.fromhex("e2 17 16 00 01 00 e4 0f 16 00 16 40 10")
    code = printed("ready\n") + read + printed("lost\n") + read + printed("won\n") + b"\xba"
    data[0x2100 : 0x2100 + len(code)] = code
    path = tmp_path / "objects.z5"
    path.write_bytes(data)
    monkeypatch.setitem(
        _profiles._PROFILES,
        sha256(data).hexdigest(),
        StoryProfile(
            7,
            frozenset({"lost"}),
            frozenset({"won"}),
            player_object=299,
            moves_global=17,
            moves_offset=-545,
            victory_score=7,
        ),
    )
    env = FernzEnv(path, seed=42)
    env.reset()
    return env


def test_public_v5_objects_keep_large_links_and_all_attributes(object_env):
    env = object_env
    before = env.get_state()
    world = env.get_world_objects()
    assert len(world) == 301 and all(len(obj.attr) == 48 for obj in world)
    assert world[0].num == 0 and not any(world[0].attr)
    assert world[300].attr == [0] * 47 + [1]
    assert env.get_player_object() == world[299] == env.get_object(299)
    assert env.get_player_location() == world[1]
    assert [obj.num for obj in env.get_inventory()] == [298, 300]
    assert env.get_object(world[300].child) == world[297]
    assert world[1].properties == [63, 62, 33] + [0] * 13
    for number in (-1, 0, 301, 65535, 65536):
        assert env.get_object(number) is None
    world[0].attr[47] = 1
    world[300].parent = 0
    world[300].attr[47] = 0
    world[1].properties.clear()
    inventory = env.get_inventory()
    inventory[0].properties[0] = 63
    assert env.get_world_objects()[0].attr[47] == 0
    assert env.get_object(300).parent == 299 and env.get_object(300).attr[47] == 1
    assert env.get_state() == before


def test_v5_copy_and_checkpoint_preserve_outcomes_and_container_queries(object_env, monkeypatch):
    env = object_env
    state = env.get_state()
    assert isinstance(state, GameState) and state.format_version == 4
    with pytest.raises(FrozenInstanceError):
        state.pc = 0
    env.game_path.unlink()
    monkeypatch.setattr("fernz._random.secrets.randbits", lambda _: pytest.fail("No entropy"))
    fork = env.copy()
    assert fork.story is env.story and fork.memory is not env.memory
    assert fork.get_state() == state
    assert fork.step("lose")[1:] == (0, False, {"score": 0, "moves": 0})
    lost = fork.get_state()
    assert fork.game_over() and not env.game_over()
    assert fork.step("win")[1:] == (7, True, {"score": 7, "moves": 0})
    won = fork.get_state()
    assert fork.victory() and fork.copy().get_state() == won
    env.set_state(won)
    assert env.get_score() == 7 and env.victory() and env.done
    assert env.get_player_location().num == 1
    assert env.get_inventory() == fork.get_inventory()
    env.set_state(lost)
    assert env.game_over() and not env.done and env.get_score() == 0
    assert env.step("win")[1:] == (7, True, {"score": 7, "moves": 0})
    assert env.get_state() == won
    env.set_state(state)
    assert env.reset()[1] == {"score": 0, "moves": 0}
    assert env.get_state() == state


@pytest.mark.parametrize("value", (0, 544, 545, 600, 1440, 65535))
def test_profiled_elapsed_time_reads_live_memory_without_execution(object_env, value):
    env = object_env
    env.memory.write_word(env.story.header.globals_table + 34, value)
    before = env.get_state()
    assert env.get_moves() == value - 545
    assert env.get_max_score() == 7 and env.get_score() == 0
    assert env.get_state() == before


def test_v5_query_failures_and_failed_snapshot_restore_are_atomic(object_env):
    env = object_env
    state = env.get_state()
    with pytest.raises(NotImplementedError, match="Cleaned"):
        env.get_world_objects(clean=True)
    with pytest.raises(TypeError):
        env.get_object("299")
    with pytest.raises(ValueError, match="different story"):
        env.set_state(replace(state, story_sha256="0" * 64))
    assert env.get_state() == state
    # Make an inventory cycle through a word-sized sibling link.
    env.memory.write_word(0xBE + 299 * 14 + 8, 298)
    before = env.get_state()
    with pytest.raises(ExecutionError, match="sibling chain"):
        env.get_inventory()
    assert env.get_state() == before
    env.set_state(state)
    with pytest.raises(ExecutionError, match="budget"):
        env.step("lose", max_steps=1)
    for query in (env.get_state, env.get_score, env.get_inventory, env.game_over):
        with pytest.raises(RuntimeError, match="reset"):
            query()
    env.set_state(state)
    assert env.get_inventory()[0].num == 298


def test_unprofiled_v5_keeps_raw_inspection_and_reports_missing_story_metadata(
    object_env, monkeypatch
):
    monkeypatch.delitem(_profiles._PROFILES, object_env.get_state().story_sha256)
    env = FernzEnv(object_env.game_path)
    assert env.reset()[1] == {}
    assert len(env.get_world_objects()) == 301
    assert env.get_object(300).attr[47] == 1
    for query in (
        env.get_score,
        env.get_moves,
        env.get_max_score,
        env.get_player_object,
        env.get_player_location,
        env.get_inventory,
        env.game_over,
        env.victory,
    ):
        with pytest.raises(NotImplementedError, match="profile"):
            query()
