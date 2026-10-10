import pytest

from fernz import ExecutionError, Memory, Story
from fernz._objects import Objects

from .story_files import program_bytes, put_word, zchars


def object_memory():
    data = bytearray(program_bytes(b"\xba"))
    # Defaults occupy 0x40..0x7d; three 9-byte entries start at 0x7e.
    put_word(data, 0x40 + 2 * 4, 0xABCD)  # Default property 5.
    for obj, table in ((1, 0x200), (2, 0x220), (3, 0x240)):
        put_word(data, 0x7E + 9 * (obj - 1) + 7, table)
    data[0x200:0x203] = b"\x01" + zchars(6, 7, 8)  # Short name "abc".
    data[0x203:0x20B] = bytes.fromhex("2a 12 34 07 56 01 78 00")  # Properties 10, 7, 1.
    data[0x7E + 6] = 2  # Object 1 contains 2 then 3.
    data[0x87 + 4] = 1
    data[0x87 + 5] = 3
    data[0x90 + 4] = 1
    return Memory(Story(data))


def test_object_links_short_names_and_attributes():
    objects = Objects(object_memory())
    assert objects.name(1) == "abc"
    assert objects.name(2) == ""
    assert objects.child(1) == 2
    assert objects.parent(2) == 1
    assert objects.sibling(2) == 3
    objects.attribute(2, 0, True)
    objects.attribute(2, 31, True)
    assert objects.memory.read_bytes(0x87, 4) == b"\x80\x00\x00\x01"
    assert objects.attribute(2, 31)
    objects.attribute(2, 0, False)
    assert not objects.attribute(2, 0)


def test_remove_and_insert_preserve_siblings_and_children():
    objects = Objects(object_memory())
    objects.remove(3)
    assert objects.sibling(2) == 0
    assert objects.parent(3) == objects.sibling(3) == 0
    objects.insert(3, 1)
    assert objects.child(1) == 3
    assert objects.sibling(3) == 2
    objects.insert(2, 3)
    assert objects.child(3) == 2
    assert objects.parent(2) == 3
    assert objects.sibling(3) == 0
    objects.remove(3)
    assert objects.child(1) == 0
    assert objects.child(3) == 2


def test_property_default_lengths_updates_and_iteration():
    objects = Objects(object_memory())
    assert objects.get(1, 10) == 0x1234
    assert objects.get(1, 7) == 0x56
    assert objects.get(1, 5) == 0xABCD
    assert objects.find(1, 5) is None
    assert [(p.number, p.address, p.size) for p in objects.properties(1)] == [
        (10, 0x204, 2),
        (7, 0x207, 1),
        (1, 0x209, 1),
    ]
    assert [objects.next_property(1, n) for n in (0, 10, 7, 1)] == [10, 7, 1, 0]
    assert objects.next_property(2, 0) == 0
    objects.put(1, 10, 0x9876)
    objects.put(1, 7, 0xFFFF)
    assert objects.get(1, 10) == 0x9876
    assert objects.get(1, 7) == 255


def test_bad_tree_and_property_operations_raise():
    objects = Objects(object_memory())
    for operation in (
        lambda: objects.parent(0),
        lambda: objects.parent(256),
        lambda: objects.attribute(1, 32),
        lambda: objects.get(1, 0),
        lambda: objects.put(1, 5, 0),
        lambda: objects.next_property(1, 5),
        lambda: objects.insert(1, 2),
    ):
        with pytest.raises(ExecutionError):
            operation()
    objects.memory.write_byte(0x87 + 5, 2)
    with pytest.raises(ExecutionError, match="Broken sibling"):
        objects.remove(3)


def test_properties_must_stay_in_dynamic_memory_and_descend():
    memory = object_memory()
    memory.write_byte(0x206, 11)
    with pytest.raises(ExecutionError, match="property order"):
        list(Objects(memory).properties(1))
    memory.write_word(0x85, 0x2FF)
    memory.write_byte(0x2FF, 1)
    with pytest.raises(ExecutionError, match="outside dynamic"):
        Objects(memory).name(1)


def test_large_properties_have_addresses_but_no_scalar_value():
    objects = Objects(object_memory())
    objects.memory.write_byte(0x203, 0xEA)  # Property 10, eight data bytes.
    assert objects.find(1, 10).size == 8
    with pytest.raises(ExecutionError, match="one- or two-byte"):
        objects.get(1, 10)
    with pytest.raises(ExecutionError, match="one- or two-byte"):
        objects.put(1, 10, 5)
