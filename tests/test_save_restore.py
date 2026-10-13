import re
from dataclasses import replace

import pytest

from fernz import FernzEnv, Memory, Story
from fernz._host_io import HostIO
from fernz._machine import Machine
from fernz._quetzal import loads
from fernz._random import RandomGenerator

from .observation_helpers import plain_text, text_response, window_text
from .save_story import save_story
from .story_files import READ, program_bytes


class Storage:
    def __init__(self, data=None):
        self.data = data
        self.saves = 0
        self.restores = 0

    def save(self, data):
        self.data = data
        self.saves += 1
        return True

    def restore(self):
        self.restores += 1
        return self.data


def results(observation):
    return [int(n) for n in re.findall(r"^R=(-?\d+)$", plain_text(observation), re.MULTILINE)]


@pytest.fixture(params=[False, True], ids=["low-addresses", "high-addresses"])
def game(tmp_path, request):
    path = tmp_path / "saves.z3"
    path.write_bytes(save_story(high=request.param))
    return path


def test_save_close_and_restore_into_fresh_environment(game):
    storage = Storage()
    first = FernzEnv(game, seed=42, save_handler=storage.save)
    first.reset()
    initial = first.get_state()
    saved_output = first.step("save")
    assert results(saved_output[0])[:4] == [7, 8, 9, 0x3333]
    assert storage.data[:4] == b"FORM"
    portable = loads(first.story, storage.data)
    assert [f.stack for f in portable.frames] == [(0x1111,), (0x2222,), (0x3333,)]
    assert [f.argument_count for f in portable.frames] == [0, 1, 3]
    assert first.story.data[portable.pc - 1] == 0xB5
    continuation = first.step("continue")
    assert results(continuation[0]) == [18, 42, 0x2222, 42, 0x1111]
    first.close()

    second = FernzEnv(game, seed=42, restore_handler=storage.restore)
    second.reset()
    assert second.get_state() == initial
    memory = second.memory
    restored_output = second.step("restore")
    assert text_response(restored_output) == text_response(saved_output)
    assert "<split 0>" in restored_output[0].stream
    assert second.memory is memory
    assert second.step("continue") == continuation
    assert storage.saves == storage.restores == 1


@pytest.mark.parametrize("seed", [5, 1000])
def test_opcode_restore_preserves_current_rng_flags_and_output(game, seed):
    storage = Storage()
    env = FernzEnv(game, seed=42, save_handler=storage.save, restore_handler=storage.restore)
    env.reset()
    env.step("save")
    env.step("continue")
    # Install a different active mode and output policy using the public host
    # checkpoint API. The opcode must retain these, rather than the saved values.
    rng = RandomGenerator(77)
    rng.random(-seed)
    rng.random(32767)
    env.set_state(replace(env.get_state(), rng=rng.get_state(), screen_enabled=False))
    env.memory.write_byte(0x11, 3)
    before = env.get_state()
    expected_draw = rng.random(32767)
    assert plain_text(env.step("restore")[0]) == ""
    after = env.get_state()
    assert after.rng == rng.get_state()
    assert after.rng.host_seed == 77
    assert after.frames[-1].locals[0] == expected_draw
    assert after.ram[0x11] == 2  # The unavailable transcript remains off.
    assert not after.screen_enabled
    assert before.ram[0x11] == after.ram[0x11]


def test_host_checkpoints_still_rewind_rng_flags_and_screen_and_keep_recipient_handlers(game):
    storage = Storage()
    source = FernzEnv(game, seed=42, save_handler=lambda _: False)
    source.reset()
    checkpoint = source.get_state()
    env = FernzEnv(
        game,
        seed=99,
        save_handler=storage.save,
        restore_handler=storage.restore,
    )
    env.set_state(checkpoint)
    expected = env.step("save")
    assert results(expected[0]) == [7, 8, 9, 0x3333, 14545]
    assert window_text(expected[0]) == expected[0].text
    env.memory.write_byte(0x11, 3)
    env.set_state(checkpoint)
    assert env.get_state() == checkpoint
    assert env.step("save") == expected
    assert storage.saves == 2  # Source's failing handler was never installed.


@pytest.mark.parametrize("opcode", [0xB5, 0xB6], ids=["save", "restore"])
@pytest.mark.parametrize("branch", [b"\xc6", b"\x80\x06", b"\x46", b"\x00\x06"])
@pytest.mark.parametrize("failure", ["unavailable", "cancel", "os-error", "bad-file"])
def test_opcode_failure_uses_its_encoded_branch(opcode, branch, failure):
    # False result: take a negated branch, otherwise fall through to F.
    code = bytes((opcode,)) + branch + bytes.fromhex("e5 7f 46 ba e5 7f 54 ba")

    def fail(*_):
        if failure == "os-error":
            raise OSError("storage unavailable")
        return False if opcode == 0xB5 else b"bad file" if failure == "bad-file" else None

    handler = None if failure == "unavailable" else fail
    io = HostIO(save=handler) if opcode == 0xB5 else HostIO(restore=handler)
    machine = Machine(Memory(Story(program_bytes(code))), io=io)
    assert machine.run() == ("F" if branch[0] & 0x80 else "T")


@pytest.mark.parametrize("branch", [b"\xc6", b"\x80\x06", b"\x46", b"\x00\x06"])
def test_save_and_successful_restore_apply_saved_branch_polarity(branch):
    storage = Storage()
    code = READ + b"\xb5" + branch + bytes.fromhex("e5 7f 46 ba e5 7f 54 ba")
    story = Story(program_bytes(code))
    machine = Machine(Memory(story), io=HostIO(save=storage.save, restore=storage.restore))
    machine.run()
    machine.accept_input("save")
    expected = "T" if branch[0] & 0x80 else "F"
    assert machine.run() == "\n" + expected
    # A fresh machine with the same ROM can resume the saved branch without
    # running the donor prefix. _restore normally runs during opcode dispatch.
    recipient = Machine(Memory(story), io=HostIO(restore=storage.restore))
    assert recipient._restore()
    assert recipient.run() == expected


@pytest.mark.parametrize("offset", [0, 1])
@pytest.mark.parametrize("store", [0, 16])
def test_save_branch_can_return_from_a_routine(offset, store):
    storage = Storage()
    code = bytes.fromhex("e0 3f 03 00") + bytes((store, 0xE6, 0xBF, store, 0xBA))
    routine = bytes((0, 0xB5, 0xC0 | offset))
    story = Story(program_bytes(code, (0x600, routine)))
    first = Machine(Memory(story), io=HostIO(save=storage.save))
    assert first.run() == str(offset)
    restored = Machine(Memory(story), io=HostIO(restore=storage.restore))
    assert restored._restore()
    assert restored.run() == str(offset)


def test_malformed_restore_does_not_change_game_state(game):
    storage = Storage()
    env = FernzEnv(game, seed=42, save_handler=storage.save, restore_handler=storage.restore)
    env.reset()
    env.step("save")
    good = storage.data
    env.step("continue")
    env.memory.write_word(0x170, 0x1234)
    before = env.get_state()
    # Every truncated prefix must fail without touching the live game. Exercise
    # the actual restore implementation, including memory/branch validation.
    for size in range(len(good)):
        storage.data = good[:size]
        assert not env._machine._restore()
        assert env.get_state() == before
    storage.data = good
    env.step("restore")
    assert env.memory.read_word(0x170) == 0


@pytest.mark.parametrize("handler", ["save_handler", "restore_handler"])
def test_handlers_must_be_callable(game, handler):
    with pytest.raises(TypeError, match="callable"):
        FernzEnv(game, **{handler: True})


def test_handler_programming_errors_are_not_reported_as_storage_failure():
    with pytest.raises(TypeError, match="bool"):
        HostIO(save=lambda _: None).write_save(b"data")
    with pytest.raises(TypeError, match="bytes"):
        HostIO(restore=lambda: "text").read_save()

    def broken(_):
        raise RuntimeError("bug")

    with pytest.raises(RuntimeError, match="bug"):
        HostIO(save=broken).write_save(b"data")


def test_opcode_restore_does_not_request_entropy(game, monkeypatch):
    from fernz import _random

    storage = Storage()
    env = FernzEnv(game, save_handler=storage.save, restore_handler=storage.restore)
    env.reset()
    env.step("save")
    env.step("continue")

    def unexpected(*_):
        pytest.fail("Opcode restore must not reseed the RNG")

    monkeypatch.setattr(_random.secrets, "randbits", unexpected)
    env.step("restore")
