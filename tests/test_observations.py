"""Public observation protocol, geometry, and replay invariants."""

from dataclasses import FrozenInstanceError, replace

import pytest

from fernz import FernzEnv, Observation

from .observation_helpers import stream_events, window_text
from .story_files import READ, program_bytes
from .test_save_restore import Storage
from .v5_story import save_story


def say(text):
    return b"".join(bytes((0xE5, 0x7F, 13 if c == "\n" else ord(c))) for c in text)


def fixture_env(tmp_path, code, *, version=5, **kwargs):
    path = tmp_path / f"display.z{version}"
    path.write_bytes(program_bytes(code, version=version))
    return FernzEnv(path, seed=42, **kwargs)


def test_observation_is_immutable_and_escapes_literal_control_text(tmp_path):
    text = "<bold> <invert> << > & text\n"
    env = fixture_env(tmp_path, say(text) + READ + b"\x10")
    observation, info = env.reset()
    assert observation == Observation("<reset><size 80 25><bottom>" + text.replace("<", "<<"), text)
    assert info == {}
    assert (
        "".join(value for kind, value in stream_events(observation.stream) if kind == "text")
        == text
    )
    with pytest.raises(FrozenInstanceError):
        observation.text = "changed"


@pytest.mark.parametrize("version", (3, 5))
def test_window_interleaving_retains_erased_upper_text(tmp_path, version):
    read = READ + (b"\x10" if version == 5 else b"")
    # Print lower A, upper B, resize (which clears V3 upper), then lower C.
    code = say("A") + bytes.fromhex("ea 7f 02 eb 7f 01") + say("B")
    code += bytes.fromhex("ea 7f 00 eb 7f 00") + say("C") + read
    env = fixture_env(tmp_path, code, version=version)
    obs, _ = env.reset()
    assert obs.text == "ABC"
    assert window_text(obs, 0) == "AC" and window_text(obs, 1) == "B"
    tail = "<split 2>"
    if version == 3:
        tail += "<clear top>"
    else:
        tail += "<at 3 1>"
    tail += "<top><at 1 1>B<split 0>"
    if version == 3:
        tail += "<clear top>"
    assert obs.stream.endswith("A" + tail + "<at 1 1><bottom>C")
    assert env.get_state().output.window == 0


def test_cursor_style_font_colour_clear_and_buffer_commands(tmp_path):
    code = bytes.fromhex("ea 7f 03 eb 7f 01 ef 5f 02 04 f1 7f 07")
    code += say("A") + bytes.fromhex("ef 5f 02 04 f1 7f 00") + say("B")
    code += bytes.fromhex("ee 7f 01 be 04 7f 04 11 1b 03 02")
    code += bytes.fromhex("be 0d 0f 00 1f 7c 00 f2 7f 00 ed 7f 01 eb 7f 00")
    code += say("C") + READ + b"\x10"
    env = fixture_env(tmp_path, code)
    obs, _ = env.reset()
    assert obs.text == "ABC"
    assert obs.stream == (
        "<reset><size 80 25><bottom><split 3><at 4 1><top><at 1 1><at 2 4>"
        "<invert><bold><italic>A<at 2 4><normal>B<clear-line><font 4>"
        "<color red black><color #ff0000 #0000ff><buffer off><clear top><at 1 1><bottom>C"
    )
    state = env.get_state().output
    assert state.styles == (0, 0) and state.fonts == (1, 4)
    assert state.colours[1] == ("#ff0000", "#0000ff") and not state.buffered
    assert state.cursors[1] == (1, 1)


def test_custom_geometry_header_copy_restore_restart_and_reset(tmp_path):
    read = READ + b"\x10"
    code = bytes.fromhex("ea 7f 03 eb 7f 01 ef 5f 03 20 f1 7f 02")
    code += say("A") + read + say("B") + read + b"\xb7"
    env = fixture_env(tmp_path, code, screen_width=128, screen_height=232)
    initial = env.reset()
    assert initial[0].stream.startswith("<reset><size 128 232>")
    assert env.memory.read_bytes(0x20, 8) == bytes((232, 128, 0, 128, 0, 232, 1, 1))
    state = env.get_state()
    assert (state.output.width, state.output.height) == (128, 232)
    expected = env.step("")
    assert not expected[0].stream.startswith("<reset>")
    env.set_state(state)
    assert env.step("") == expected
    recipient = FernzEnv(env.game_path)
    recipient.set_state(state)
    assert (recipient.screen_width, recipient.screen_height) == (128, 232)
    assert recipient.copy().step("") == expected
    assert recipient.step("") == expected
    # Restart retains host geometry and emits the story's actual operations.
    restart = recipient.step("")[0]
    assert "<reset>" not in restart.stream
    assert recipient.memory.read_byte(0x21) == 128
    assert recipient.reset() == initial


def test_header_and_display_geometry_must_agree_atomically(tmp_path):
    env = fixture_env(tmp_path, READ + b"\x10")
    env.reset()
    before = env.get_state()
    malformed = replace(before, output=replace(before.output, width=100))
    with pytest.raises(ValueError, match="protected header"):
        env.set_state(malformed)
    assert env.get_state() == before


@pytest.mark.parametrize("width,height", [(1, 1), (255, 254), (128, 232)])
def test_geometry_limits_are_consistent(tmp_path, width, height):
    env = fixture_env(tmp_path, READ + b"\x10", screen_width=width, screen_height=height)
    env.reset()
    env.set_state(env.get_state())
    assert env.memory.read_word(0x22) == width
    assert env.memory.read_word(0x24) == height


@pytest.mark.parametrize(
    "name,value,error",
    [
        ("screen_width", 0, ValueError),
        ("screen_width", 256, ValueError),
        ("screen_height", 0, ValueError),
        ("screen_height", 255, ValueError),
        ("screen_width", True, TypeError),
        ("screen_height", 3.5, TypeError),
    ],
)
def test_invalid_geometry_is_rejected(tmp_path, name, value, error):
    with pytest.raises(error):
        fixture_env(tmp_path, READ + b"\x10", **{name: value})


def test_quetzal_keeps_recipient_geometry(tmp_path):
    path = tmp_path / "save.z5"
    path.write_bytes(save_story())
    storage = Storage()
    donor = FernzEnv(path, save_handler=storage.save, screen_width=128, screen_height=232)
    donor.reset()
    donor.step("save")
    recipient = FernzEnv(path, restore_handler=storage.restore, screen_width=60, screen_height=20)
    recipient.reset()
    recipient.step("restore")
    assert recipient.memory.read_bytes(0x20, 8) == bytes((20, 60, 0, 60, 0, 20, 1, 1))
    assert recipient.get_state().output.width == 60


def test_unprofiled_prompt_and_questions_are_preserved(tmp_path):
    env = fixture_env(tmp_path, say("Which > value?\n>") + READ + b"\x10")
    obs, _ = env.reset()
    assert obs.text == "Which > value?\n>"
    assert obs.stream.endswith(obs.text)


@pytest.mark.parametrize("version", (3, 5))
def test_redirected_and_disabled_text_stays_out_of_observation_and_callback(tmp_path, version):
    parts = []
    code = say("A") + bytes.fromhex("f3 4f 03 02 40") + say("<hidden>")
    code += bytes.fromhex("f3 3f ff fd f3 3f ff ff") + say("disabled")
    code += bytes.fromhex("ea 7f 02 eb 7f 01 f3 7f 01") + say("B")
    code += READ + (b"\x10" if version == 5 else b"")
    env = fixture_env(tmp_path, code, version=version, output_handler=parts.append)
    obs, _ = env.reset()
    assert obs.text == "".join(parts) == "AB"
    assert "".join(value for kind, value in stream_events(obs.stream) if kind == "text") == "AB"
    assert "<top>" in obs.stream
    assert env.memory.read_word(0x240) == 8
    assert env.memory.read_bytes(0x242, 8) == b"<hidden>"


def test_inactive_cursor_moves_do_not_change_window_selection(tmp_path):
    # Erase the lower window while upper is selected, then clear all without
    # unsplitting, and finally clear all with unsplitting and cursor resets.
    code = bytes.fromhex("ea 7f 03 eb 7f 01 ef 5f 02 04 ed 7f 00")
    code += say("A") + bytes.fromhex("ed 3f ff fe") + say("B")
    code += bytes.fromhex("ed 3f ff ff") + say("C") + READ + b"\x10"
    env = fixture_env(tmp_path, code)
    obs, _ = env.reset()
    assert "<clear bottom><at 4 1 bottom>A<clear all>B" in obs.stream
    assert obs.stream.endswith("<clear all><split 0><bottom><at 1 1><at 1 1 top>C")
    assert window_text(obs, 1) == "AB"
    assert window_text(obs, 0) == "C"
    assert env.get_state().output.cursors == ((1, 2), (1, 1))


@pytest.mark.parametrize(
    "changes",
    [
        {"styles": (0, 16)},
        {"styles": [0, 0]},
        {"colours": (("white", "black"), ("#abcdefg", "black"))},
        {"colours": (["white", "black"], ("white", "black"))},
        {"buffered": 1},
        {"cursors": ((1, 82), (1, 1))},
        {"height": 255},
    ],
)
def test_malformed_display_checkpoints_leave_live_state_intact(tmp_path, changes):
    env = fixture_env(tmp_path, READ + b"\x10")
    env.reset()
    state = env.get_state()
    with pytest.raises((TypeError, ValueError)):
        env.set_state(replace(state, output=replace(state.output, **changes)))
    assert env.get_state() == state


@pytest.mark.rom
@pytest.mark.smoke
def test_zork_prompt_stays_in_stream_and_questions_stay_in_text(jericho_games):
    env = FernzEnv(jericho_games / "zork1.z5", seed=12)
    try:
        initial, _ = env.reset()
        assert initial.stream.endswith("\n>") and initial.text.endswith("\n")
        assert initial.stream.startswith("<reset><size 80 25><bottom><at 25 1>")
        turn = env.step("look")[0]
        assert turn.stream == turn.text + ">"
        question = env.step("restart")[0]
        assert "Do you wish to restart?" in question.text
        assert question.stream == question.text + " >"
        state = env.get_state()
        continued = env.step("no")
        env.set_state(state)
        assert env.step("no") == continued
    finally:
        env.close()


@pytest.mark.parametrize(
    "true,default,current,white,black", [(False, 1, 0, 9, 2), (True, -1, -2, 0x7FFF, 0)]
)
def test_colour_stream_retains_default_intent_without_changing_vm_state(
    tmp_path, true, default, current, white, black
):
    from fernz._output import Output

    env = fixture_env(tmp_path, READ + b"\x10")
    env.reset()
    output = Output(env.memory)
    output.colour(white, black, true=true)
    output.emit("A")
    output.colour(default, current, true=true)
    output.emit("B")
    output.colour(current, default, true=true)
    output.emit("C")
    stream = output.drain()
    assert "<color default current>B<color current default>C" in stream
    assert output.state.colours[0] == ("white", "black")
