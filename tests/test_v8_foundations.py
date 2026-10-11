"""Independent V8 examples from Standard 1.1 §1 and its V5-equivalence rule."""

import io
import sys

import pytest

from fernz import FernzEnv, Memory, Story, _cli
from fernz._machine import Machine
from fernz._output import Output
from fernz._text import Text

from .story_files import READ, program_bytes, put_word, zchars

AREAD = READ + b"\x10"


def large_story():
    # call_1s packed 0x8000 -> byte 0x40000, then read the result and quit.
    # The callee prints a packed string above 256 KiB and pauses in high memory.
    return Story(
        program_bytes(
            bytes.fromhex("88 80 00 11 e6 bf 11 ba"),
            (0x40000, b"\x01" + bytes.fromhex("8d 90 00") + AREAD + b"\x9b\x2a"),
            (0x48000, zchars(6, 7, 8)),
            version=8,
            size=0x50000,
        )
    )


def test_v8_high_routine_and_string_addresses_and_zero_initialized_locals():
    story = large_story()
    assert story.size == 0x50000 and story.header.entry_address == 0x401
    m = Machine(Memory(story), seed=42)
    assert m.run() == "abc"
    assert m.pc > 0x40000 and m.frames[-1].locals == [0]
    assert m.input_request.instruction_address == 0x40004
    m.accept_input("LOOK")
    assert m.run() == "\n42" and m.halted
    assert m.memory.read_bytes(0x282, 4) == b"look"


def test_v8_high_pc_survives_public_checkpoint_and_copy(tmp_path):
    path = tmp_path / "high.z8"
    path.write_bytes(large_story().data)
    env = FernzEnv(path, seed=42)
    try:
        assert env.reset()[0].text == "abc"
        state = env.get_state()
        fork = env.copy()
        try:
            expected = env.step("look")
            assert env.done and fork.get_state() == state
            assert fork.step("look") == expected
            env.set_state(state)
            assert env.step("look") == expected
            assert env.get_state() == fork.get_state()
        finally:
            fork.close()
    finally:
        env.close()


def test_v8_ignores_v6_v7_offsets_and_abbreviations_stay_word_addressed():
    data = bytearray(
        program_bytes(AREAD, (0x800, b"\x01\x06"), (0x820, zchars(29, 30, 31)), version=8)
    )
    put_word(data, 0x18, 0x700)
    put_word(data, 0x700, 0x410)  # 2 * 0x410, not 8 * 0x410.
    put_word(data, 0x28, 0x1234)
    put_word(data, 0x2A, 0x5678)
    data[0x800:0x802] = zchars(1, 0, 5)
    story = Story(data)
    assert story.header.unpack_routine_address(0x8000) == 0x40000
    assert story.header.unpack_string_address(0x9000) == 0x48000
    assert Text(Memory(story)).decode(0x800) == "xyz"


@pytest.mark.parametrize("version", (5, 8))
def test_v5_family_header_and_implicit_upper_window_growth(version):
    m = Machine(
        Memory(Story(program_bytes(AREAD, version=version))), screen_width=40, screen_height=20
    )
    assert m.memory.read_bytes(0x20, 8) == bytes((20, 40, 0, 40, 0, 20, 1, 1))
    display = Output(m.memory, m.display.state)
    display.split(1)
    display.select(1)
    display.move(3, 41)
    assert display.state.split_lines == 3 and display.state.cursors[1] == (3, 1)


def test_v8_cli_opens_and_accepts_eof(tmp_path, monkeypatch, capsys):
    path = tmp_path / "opening.z8"
    path.write_bytes(large_story().data)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert _cli.main([str(path)]) == 0
    assert capsys.readouterr().out == "abc"
