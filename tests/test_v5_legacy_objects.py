"""Bounded compatibility for duplicate properties and absent-object moves."""

import pytest

from fernz import ExecutionError, FernzEnv, Memory, Story
from fernz._objects import Objects

from .test_save_restore import results
from .v5_legacy_story import duplicate_story, zero_story


def test_duplicate_properties_preserve_order_and_update_only_the_first(tmp_path):
    path = tmp_path / "duplicates.z5"
    path.write_bytes(duplicate_story())
    env = FernzEnv(path)
    assert results(env.reset()[0]) == [11, 9, 33, 99]
    objects = Objects(env.memory)
    props = list(objects.properties(1))
    assert [p.number for p in props] == [9, 9, 8]
    assert [env.memory.read_word(p.address) for p in props] == [99, 22, 33]
    assert objects.snapshot(1).properties == [9, 9, 8] + [0] * 13
    assert objects.find(1, 7) is None
    assert objects.next_property(1, 8) == 0


@pytest.mark.parametrize("source,destination", ((0, 2), (1, 0), (0, 0)))
def test_zero_insertion_does_not_detach_an_existing_child(tmp_path, source, destination):
    path = tmp_path / "zero.z5"
    path.write_bytes(zero_story(source, destination))
    env = FernzEnv(path)
    assert results(env.reset()[0]) == [2, 1]
    objects = Objects(env.memory)
    assert objects.parent(1) == 2 and objects.child(2) == 1
    assert objects.sibling(1) == 0
    # The opcode extension does not create a public or low-level object zero.
    assert env.get_object(0) is None
    with pytest.raises(ExecutionError, match="object number 0"):
        objects.insert(1, 0)


def test_duplicate_compatibility_keeps_order_number_and_bounds_validation():
    memory = Memory(Story(duplicate_story()))
    objects = Objects(memory)
    props = list(objects.properties(1))
    memory.write_byte(props[1].address - 1, 0x4A)
    with pytest.raises(ExecutionError, match="property order"):
        list(objects.properties(1))
    memory.write_byte(props[1].address - 1, 0x40)
    with pytest.raises(ExecutionError, match="property order"):
        list(objects.properties(1))
    memory.write_word(0xCA, memory.story.header.static_memory - 1)
    memory.write_byte(memory.story.header.static_memory - 1, 1)
    with pytest.raises(ExecutionError, match="outside dynamic"):
        list(objects.properties(1))
