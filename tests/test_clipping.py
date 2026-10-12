"""Independent cursor/painting probes; no commercial game data."""

from dataclasses import replace

import pytest

from fernz import FernzEnv, Memory, Observation, ScreenOutputClipped, Story
from fernz._output import Output
from fernz._state import OutputState

from .story_files import READ, program_bytes

AREAD = READ + b"\x10"
KEY = bytes.fromhex("f6 7f 01 11")
# Sherlock-shaped box: split 23, visible row 24, then off-screen border 25.
# Leave the cursor off screen so checkpoint/character-input tests can observe it.
CLIP = bytes.fromhex(
    "ea 7f 17 eb 7f 01 ef 5f 18 14 e5 7f 56 ef 5f 19 14 f1 7f 01 e5 7f 20 e5 7f 20"
)
LOWER = bytes.fromhex("f1 7f 00 eb 7f 00 ea 7f 01")


def environment(tmp_path, code, *, height=24, **kwargs):
    path = tmp_path / "clipping.z5"
    path.write_bytes(program_bytes(code, version=5))
    return FernzEnv(path, screen_width=78, screen_height=height, **kwargs)


@pytest.mark.parametrize("height", [24, 25, 34])
def test_box_reports_only_actual_offscreen_painting(tmp_path, height):
    env = environment(tmp_path, CLIP + KEY + LOWER + AREAD, height=height)
    obs, _ = env.reset()
    assert obs.text == "V  "  # Transcript and raw stream retain clipped spaces.
    assert obs.stream.endswith("<invert>  ")
    assert obs.diagnostics == (
        (ScreenOutputClipped(78, 24, 1, 2, 25, 25, 20, 21),) if height == 24 else ()
    )
    state = env.get_state()
    assert state.output.cursors[1] == (25, 22)
    assert state.output.split_lines == min(25, height)
    assert env.step("x")[0].diagnostics == ()
    env.set_state(state)
    assert env.get_state() == state
    assert env.step("x")[0].diagnostics == ()  # Old diagnostics are not replayed.
    assert Observation("", "").diagnostics == ()


def test_offscreen_move_and_newline_without_painting_do_not_warn(tmp_path):
    code = bytes.fromhex("ea 7f 17 eb 7f 01 ef 5f 19 14 bb") + KEY
    env = environment(tmp_path, code + bytes.fromhex("e5 7f 58") + KEY)
    assert env.reset()[0].diagnostics == ()
    assert env.get_state().output.cursors[1] == (26, 1)
    assert env.step("x")[0].diagnostics == (ScreenOutputClipped(78, 24, 1, 1, 26, 26, 1, 1),)


@pytest.mark.parametrize("version", [4, 5, 8])
def test_cursor_and_split_remain_bounded_without_overwriting_visible_cells(version):
    memory = Memory(Story(program_bytes(b"\xba", version=version)))
    display = Output(memory, OutputState(width=2, height=2))
    display.split(3)
    assert display.state.split_lines == 2
    display.select(1)
    display.move(2, 1)
    display.emit("ABCD\nE")
    assert display.state.cursors[1] == (4, 2)
    assert display.drain_diagnostics() == (ScreenOutputClipped(2, 2, 1, 3, 3, 4, 1, 2),)
    display.state._validate(memory.story)
    display.move(0xFFFF, 1)
    display.emit("\nX")
    assert display.state.cursors[1] == (0xFFFF, 2)
    display.state._validate(memory.story)
    with pytest.raises(ValueError, match="Cursor row"):
        replace(display.state, cursors=((3, 1), (1, 1)))._validate(memory.story)


def test_stream_three_and_disabled_screen_do_not_report_clipping(tmp_path):
    offscreen = bytes.fromhex("ea 7f 17 eb 7f 01 ef 5f 19 14")
    # stream 3 table; print X; close stream; screen off; print Y; screen on.
    code = (
        offscreen
        + bytes.fromhex("f3 4f 03 02 50 e5 7f 58 f3 3f ff fd f3 3f ff ff e5 7f 59 f3 7f 01")
        + KEY
    )
    env = environment(tmp_path, code)
    obs, _ = env.reset()
    assert obs.text == "" and obs.diagnostics == ()
    assert env.memory.read_word(0x250) == 1
    assert env.memory.read_byte(0x252) == ord("X")


def test_get_cursor_and_quetzal_restore_preserve_offscreen_continuation(tmp_path):
    saved = []
    # Save at an off-screen cursor, then read a key and restore. The restored
    # save returns 2 and suspends on the same key request with no fresh output.
    code = CLIP + bytes.fromhex("f0 3f 02 50 be 00 ff 10") + KEY
    code += bytes.fromhex("be 01 ff 12 ba")
    env = environment(
        tmp_path,
        code,
        save_handler=lambda data: saved.append(data) or True,
        restore_handler=lambda: saved[-1],
    )
    assert env.reset()[0].diagnostics
    assert env.memory.read_word(0x250) == 25
    assert env.memory.read_word(0x252) == 22
    restored = env.step("x")[0]
    assert restored.diagnostics == ()
    assert env.get_state().output.cursors[1] == (25, 22)
    assert env.memory.read_word(env.story.header.globals_table) == 2
