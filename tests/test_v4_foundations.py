"""Independent V4 examples for the boundaries between V3 and V5 semantics."""

import io
import sys
from dataclasses import replace

import pytest

from fernz import FernzEnv, Memory, Story, UnsupportedOpcodeError, _cli
from fernz._machine import Machine
from fernz._objects import Objects
from fernz._state import StoredInputRequest
from fernz._text import Text

from .story_files import READ, program_bytes, put_word, zchars


def machine(code, *chunks, **kwargs):
    return Machine(Memory(Story(program_bytes(code, *chunks, version=4))), **kwargs)


def test_v4_calls_use_packed_addresses_default_locals_and_seven_arguments():
    code = bytes.fromhex("ec 15 55 40 00 01 02 03 04 05 06 07 11") + READ
    # Print default local 8, a high packed string, then return argument 7.
    routine = b"\x08" + b"\x00\x63" * 8 + bytes.fromhex("e6 bf 08 8d 44 00 ab 07")
    story = Story(
        program_bytes(code, (0x10000, routine), (0x11000, zchars(6, 7, 8)), version=4, size=0x14000)
    )
    m = Machine(Memory(story))
    assert m.run() == "99abc"
    assert m.read_variable(17) == 7 and len(m.frames) == 1


def test_v4_header_configures_only_v4_fields():
    data = bytearray(program_bytes(READ, version=4))
    data[1] = 0xFF
    data[0x22:0x30] = bytes(range(14))
    m = Machine(Memory(Story(data)), screen_width=40, screen_height=18)
    assert m.memory.read_byte(1) == 0x73  # Preserve undefined bits, advertise fixed font only.
    assert m.memory.read_bytes(0x1E, 4) == bytes((6, ord("F"), 18, 40))
    assert m.memory.read_bytes(0x22, 14) == bytes(range(14))
    assert m.memory.read_word(0x32) == 0
    assert not m.memory.read_word(0x10) & 1


def test_v4_sread_has_no_result_byte_and_uses_nul_terminated_input():
    m = machine(READ + bytes.fromhex("e5 7f 41 ba"), (0x280, b"\x06" + b"\xcc" * 7))
    assert m.run() == ""
    assert type(m.input_request).__name__ == "InputRequest"
    m.accept_input("ABCDEF")
    assert m.run() == "\nA" and m.halted
    assert m.memory.read_bytes(0x280, 8) == b"\x06abcde\x00\xcc"
    assert m.memory.read_bytes(0x2A1, 5) == bytes((1, 0, 0, 5, 1))
    assert len(Text(m.memory).encode_dictionary(b"abcdefghi")) == 6


@pytest.mark.parametrize(
    "operands", ["02 80 02 a0 00 00", "02 80 02 a0 00 80", "02 80 02 a0 01 00"]
)
def test_v4_zero_timing_operand_leaves_an_ordinary_read(operands):
    m = machine(bytes.fromhex("e4 05 " + operands) + b"\xba")
    m.run()
    m.accept_input("look")
    assert m.run() == "\n" and m.halted


def test_v4_timed_input_is_unadvertised_and_fails_explicitly():
    m = machine(bytes.fromhex("e4 05 02 80 02 a0 01 80"))
    assert not m.memory.read_byte(1) & 0x80
    with pytest.raises(UnsupportedOpcodeError, match="Timed input"):
        m.run()


def test_v4_character_read_survives_checkpoint_copy_and_restore(tmp_path):
    path = tmp_path / "keys.z4"
    path.write_bytes(program_bytes(bytes.fromhex("f6 7f 01 10 e5 bf 10 ba"), version=4))
    env = FernzEnv(path, seed=42)
    assert not env.awaiting_character
    env.reset()
    assert env.awaiting_character
    before = env.get_state()
    assert isinstance(before.input_request, StoredInputRequest)
    assert before.input_request.character
    fork = env.copy()
    assert fork.awaiting_character
    try:
        response = env.step("Z")
        assert response[0].text == "Z" and env.done
        assert not env.awaiting_character
        env.set_state(before)
        assert env.step("Z") == fork.step("Z") == response
        assert env.get_state() == fork.get_state()
        invalid = replace(before, input_request=replace(before.input_request, character=False))
        with pytest.raises(ValueError, match="Stored input"):
            env.set_state(invalid)
    finally:
        fork.close()
        env.close()


def test_v4_objects_use_six_attribute_bytes_word_links_and_long_properties():
    data = bytearray(program_bytes(READ, version=4))
    entry = 0x40 + 126
    put_word(data, entry + 12, 0x200)
    # Property 63 with 64 data bytes; property 2 with a scalar word.
    data[0x200:0x245] = b"\x00\xbf\x80" + bytes(range(64)) + b"\x42\x12"
    data[0x245:0x247] = b"\x34\x00"
    objects = Objects(Memory(Story(data)))
    objects.attribute(1, 47, True)
    assert objects.attribute(1, 47)
    assert objects.get(1, 2) == 0x1234
    assert objects.next_property(1, 63) == 2
    assert objects.property_length(objects.find(1, 63).address) == 64


@pytest.mark.parametrize("window", (-1, 0, 1))
def test_v4_clear_and_split_keep_lower_cursor_at_bottom(window):
    m = machine(READ, screen_width=30, screen_height=12)
    display = m.display
    assert display.state.cursors[0] == (12, 1)
    assert display.drain().endswith("<at 12 1>")
    display.split(3)
    assert "<clear top>" not in display.drain()
    display.select(1)
    display.move(2, 7)
    display.erase(window)
    assert display.state.cursors[0] == (12, 1)
    if window != 0:
        assert display.state.cursors[1] == (1, 1)
    display.select(0)
    display.move(2, 5)  # V4 ignores cursor positioning in the lower window.
    display.emit("a\nb")
    assert display.state.cursors[0] == (12, 2)


def test_v4_cli_opens_without_optional_ui(tmp_path, monkeypatch, capsys):
    path = tmp_path / "opening.z4"
    path.write_bytes(program_bytes(bytes.fromhex("e5 7f 41") + READ, version=4))
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert _cli.main(["--simple", str(path)]) == 0
    assert capsys.readouterr().out == "A"
