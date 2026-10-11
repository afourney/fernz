"""Unavailable external streams must leave V3/V5 play and header state usable."""

from dataclasses import replace

import pytest

from fernz import FernzEnv

from .story_files import READ, program_bytes


def environment(tmp_path, code, version):
    path = tmp_path / f"streams.z{version}"
    path.write_bytes(program_bytes(code, version=version))
    return FernzEnv(path, seed=42)


@pytest.mark.parametrize("version", (3, 4, 5))
@pytest.mark.parametrize(
    "selection",
    ("f3 7f 02", "f3 3f ff fe", "f3 7f 04", "f3 3f ff fc", "f4 7f 01"),
    ids=("transcript-on", "transcript-off", "recording-on", "recording-off", "file-input"),
)
def test_unavailable_streams_allow_output_input_and_checkpoint_replay(tmp_path, version, selection):
    read = READ + (b"\x10" if version == 5 else b"")
    code = bytes.fromhex("e5 7f 41 " + selection + " e5 7f 42")
    code += read + bytes.fromhex("e5 7f 43 ba")
    env = environment(tmp_path, code, version)
    assert env.reset()[0].text == "AB"
    assert env.memory.read_word(0x10) & 1 == 0
    saved = env.get_state()
    expected = env.step("look")
    assert expected[0].text == "\nC" and expected[2]
    env.set_state(saved)
    assert env.step("look") == expected


@pytest.mark.parametrize("version", (3, 4, 5))
@pytest.mark.parametrize("write", ("e2 57 10 01 03", "e1 57 10 00 03"), ids=("storeb", "storew"))
def test_direct_transcript_flag_requests_report_unavailable_before_next_instruction(
    tmp_path, version, write
):
    read = READ + (b"\x10" if version == 5 else b"")
    # Request transcript and fixed font, then read/print the actual Flags 2 byte.
    code = bytes.fromhex(write + " 10 10 01 13 e6 bf 13") + read
    env = environment(tmp_path, code, version)
    assert env.reset()[0].text == "2"
    assert env.memory.read_word(0x10) == 2
    assert env.copy().get_state() == env.get_state()
    env.memory.write_bytes(0x10, b"\x00\x03")
    assert env.memory.read_word(0x10) == 2


@pytest.mark.parametrize("version", (3, 4, 5))
def test_checkpoint_cannot_enable_an_unavailable_transcript(tmp_path, version):
    read = READ + (b"\x10" if version == 5 else b"")
    env = environment(tmp_path, read, version)
    env.reset()
    saved = env.get_state()
    ram = saved.ram[:0x11] + b"\x03" + saved.ram[0x12:]
    env.set_state(replace(saved, ram=ram))
    assert env.memory.read_word(0x10) == 2
    assert len(env.memory) == env.story.size
    copied = env.memory.copy()
    copied.write_byte(0x11, 3)
    assert copied.read_byte(0x11) == 2
