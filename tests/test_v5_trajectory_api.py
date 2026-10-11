"""Independent regressions for the broader V5 trajectory milestone."""

import pytest

from fernz import ExecutionError, Memory, Story
from fernz._machine import Machine
from fernz._objects import Objects
from fernz._output import Output
from fernz._profiles import _PROFILES, StoryProfile

from .story_files import program_bytes
from .test_v5_foundations import AREAD, machine, object_memory
from .vector_archive import digest


def test_box_quote_cursor_expands_upper_window_within_screen():
    display = Output(machine(AREAD).memory)
    display.split(23)
    display.select(1)
    display.move(24, 21)
    assert display.state.split_lines == 24
    assert display.state.cursors == ((25, 1), (24, 21))
    before = display.state
    display.move(24, 81)
    assert display.state.cursors[1] == (24, 1)
    assert display.state.split_lines == before.split_lines
    before = display.state
    for position in ((26, 1), (0, 1), (25, 0)):
        with pytest.raises(ExecutionError, match="outside"):
            display.move(*position)
        assert display.state == before
    assert Output(display.memory, before).state == before


def test_profiled_raw_inspection_preserves_order_without_weakening_execution(monkeypatch):
    memory = object_memory()
    table = memory.read_word(0xCA)
    memory.write_bytes(table, bytes.fromhex("00 08 0b 0a 16 00"))
    with pytest.raises(ExecutionError, match="property order"):
        Objects(memory).snapshot(1)
    profile = StoryProfile(0, frozenset(), frozenset(), unordered_inspection_objects=frozenset({1}))
    monkeypatch.setitem(_PROFILES, digest(memory.story.data[: memory.story.size]), profile)
    objects = Objects(memory)
    assert objects.snapshot(1).properties == [8, 10] + [0] * 14
    with pytest.raises(ExecutionError, match="property order"):
        list(objects.properties(1))


def test_exact_image_attribute_write_quirk_survives_checkpoint(monkeypatch):
    data = program_bytes(
        bytes.fromhex("0b 01 30") + AREAD + bytes.fromhex("0c 01 30") + AREAD, version=5
    )
    story = Story(data)
    profile = StoryProfile(0, frozenset(), frozenset(), ignored_attribute_writes=frozenset({48}))
    monkeypatch.setitem(_PROFILES, digest(story.data[: story.size]), profile)
    original = Machine(Memory(story), seed=42)
    original.run()
    before = original.get_state()
    restored = Machine.from_state(Memory(story), before)
    for env in (original, restored):
        env.accept_input("continue")
        env.run()
    assert original.get_state() == restored.get_state()
    assert original.memory.read_bytes(0xBE, 14) == before.ram[0xBE:0xCC]
    # A different image does not acquire this behavior merely by sharing
    # header identity fields with a supported story.
    other = bytearray(data)
    other[-1] ^= 1
    with pytest.raises(ExecutionError, match="Invalid attribute 48"):
        Machine(Memory(Story(other))).run()


@pytest.mark.parametrize("code", ("0a 01 30 c2", "0b 01 31", "0c 01 31"))
def test_unprofiled_out_of_range_attributes_still_fail(code):
    with pytest.raises(ExecutionError, match="Invalid attribute"):
        machine(bytes.fromhex(code) + AREAD).run()
