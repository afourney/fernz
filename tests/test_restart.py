"""V3 restart semantics, independently assembled stories, and host boundaries."""

from dataclasses import replace
from random import Random

import pytest

from fernz import ExecutionError, FernzEnv, Memory, Story
from fernz._machine import Machine

from .observation_helpers import plain_text, text_response, window_text
from .restart_story import restart_story
from .story_files import READ, program_bytes


@pytest.mark.parametrize("flags2", range(4))
@pytest.mark.parametrize("opcode_seed", [5, 1000])
def test_restart_discards_nested_state_and_preserves_flags_and_output(
    tmp_path, flags2, opcode_seed
):
    path = tmp_path / "restart.z3"
    data = restart_story(opcode_seed=opcode_seed, flags2=flags2)
    path.write_bytes(data)
    env = FernzEnv(path, seed=42)
    assert text_response(env.reset()) == ("R=14545\n", {"score": 0, "moves": 0})
    initial = env.get_state()
    memory = env.memory
    for _ in range(2):
        env.step("descend")
        nested = env.get_state()
        assert len(nested.frames) == 3
        assert [f.stack for f in nested.frames] == [(0x1111,), (0x2222,), (0x3333,)]
        assert env.memory.read_byte(0x200) == 0xAA
        result = env.step("again")
        assert text_response(result) == ("\nR=55\nR=14545\n", -73, False, {"score": 0, "moves": 0})
        assert window_text(result[0]) == "\nR=55\nR=14545\n"
        assert env.memory is memory
        ram = bytearray(initial.ram)
        ram[0x10:0x12] = (flags2 & ~1).to_bytes(2, "big")
        assert env.get_state() == replace(initial, ram=bytes(ram))
    assert path.read_bytes() == data
    assert plain_text(env.reset()[0]) == "R=14545\n"
    assert env.get_state() == initial  # Host reset still clears Flags 2.


@pytest.mark.parametrize(
    "seed,expected",
    [
        (0, [1, 1]),
        (42, [14545, 14545]),
        (None, [Random(42).randrange(1, 32768), Random(1000).randrange(1, 32768)]),
    ],
)
def test_restart_uses_host_seed_policy_and_leaves_predictable_mode(
    tmp_path, monkeypatch, seed, expected
):
    entropy = iter([42, 1000])
    requests = []

    def draw(bits):
        requests.append(bits)
        return next(entropy)

    monkeypatch.setattr("fernz._random.secrets.randbits", draw)
    path = tmp_path / "restart.z3"
    path.write_bytes(restart_story())
    env = FernzEnv(path, seed=seed)
    assert plain_text(env.reset()[0]) == f"R={expected[0]}\n"
    env.step("descend")
    assert env.get_state().rng.period == 5
    assert plain_text(env.step("again")[0]) == f"\nR=55\nR={expected[1]}\n"
    assert env.get_state().rng.period == 0
    assert env.get_state().rng.host_seed == seed
    assert requests == ([256, 256] if seed is None else [])


def test_restart_uses_host_seed_from_restored_checkpoint(tmp_path):
    path = tmp_path / "restart.z3"
    path.write_bytes(restart_story())
    donor = FernzEnv(path, seed=42)
    donor.reset()
    donor.step("descend")
    saved = donor.get_state()
    recipient = FernzEnv(path, seed=1000)
    recipient.set_state(saved)
    expected = donor.step("again")
    assert recipient.step("again") == expected
    assert recipient.get_state() == donor.get_state()
    recipient.set_state(saved)
    assert recipient.step("again") == expected  # Checkpoints stay reusable.


def test_restart_retains_screen_selection_until_the_story_changes_it(tmp_path):
    path = tmp_path / "streams.z3"
    # Print A, select the screen, print B, read; deselect the screen and restart.
    path.write_bytes(
        program_bytes(
            bytes.fromhex("e5 7f 41 f3 7f 01 e5 7f 42") + READ + bytes.fromhex("f3 3f ff ff b7")
        )
    )
    env = FernzEnv(path, seed=42)
    assert plain_text(env.reset()[0]) == "AB"
    for _ in range(2):
        assert plain_text(env.step("again")[0]) == "\nB"


def test_restart_retains_storage_callbacks(tmp_path):
    path = tmp_path / "callbacks.z3"
    path.write_bytes(program_bytes(READ + bytes.fromhex("b5 c2 b6 c2 b7")))
    calls = []

    def save(data):
        assert data.startswith(b"FORM")
        calls.append("save")
        return False

    def restore():
        calls.append("restore")
        return None

    env = FernzEnv(path, save_handler=save, restore_handler=restore)
    env.reset()
    env.step("again")
    env.step("again")
    assert calls == ["save", "restore"] * 2


def test_restart_does_not_renew_the_instruction_budget(tmp_path):
    machine = Machine(Memory(Story(program_bytes(b"\xb7"))), seed=42)
    with pytest.raises(ExecutionError, match=r"budget \(7\) exhausted at 0x401"):
        machine.run(max_steps=7)
    path = tmp_path / "restart.z3"
    path.write_bytes(program_bytes(READ + b"\xb7"))
    env = FernzEnv(path, seed=42)
    env.reset()
    saved = env.get_state()
    assert plain_text(env.step("again", max_steps=2)[0]) == "\n"
    with pytest.raises(ExecutionError, match=r"budget \(1\)"):
        env.step("again", max_steps=1)
    with pytest.raises(RuntimeError, match="reset"):
        env.get_state()
    env.set_state(saved)
    assert plain_text(env.step("again", max_steps=2)[0]) == "\n"
