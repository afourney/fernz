"""V4 store-result saves, high addresses and deterministic host checkpoints."""

from dataclasses import replace

import pytest

from fernz import FernzEnv, Memory, Story
from fernz._host_io import HostIO
from fernz._machine import Machine
from fernz._quetzal import loads
from fernz._random import RandomGenerator

from .story_files import READ, program_bytes
from .test_save_restore import Storage
from .v4_story import save_story


@pytest.mark.parametrize("store", (0, 8))
@pytest.mark.parametrize("high", (False, True))
def test_v4_save_restore_resumes_store_byte_in_seven_argument_routine(tmp_path, store, high):
    path = tmp_path / "save.z4"
    path.write_bytes(save_story(store=store, high=high))
    storage = Storage()
    env = FernzEnv(path, seed=42, save_handler=storage.save, restore_handler=storage.restore)
    try:
        env.reset()
        assert env.step("save")[0].text == "\n1\n"
        saved = loads(env.story, storage.data)
        assert saved.frames[1].argument_count == 7
        assert saved.frames[1].locals[:7] == tuple(range(1, 8))
        assert saved.frames[1].store == 17 and saved.frames[1].stack == (0x2222,)
        assert env.memory.read_byte(saved.pc) == store
        assert (saved.pc > 0xFFFF) is high
        expected = env.step("continue")
        assert expected[0].text == "\n8738\n7\n"
        env.reset()
        assert env.step("restore")[0].text == "\n2\n"
        assert env.step("continue") == expected
    finally:
        env.close()


def test_v4_restore_preserves_rng_flags_geometry_and_screen_selection(tmp_path):
    path = tmp_path / "save.z4"
    path.write_bytes(save_story())
    storage = Storage()
    env = FernzEnv(path, seed=42, save_handler=storage.save, restore_handler=storage.restore)
    env.reset()
    env.step("save")
    checkpoint = env.get_state()
    env.reset()
    rng = RandomGenerator(1000)
    rng.random(100)
    state = env.get_state()
    env.set_state(replace(state, rng=rng.get_state(), screen_enabled=False))
    env.memory.write_byte(0x11, 2)
    before = env.get_state()
    assert env.step("restore")[0].text == ""
    after = env.get_state()
    assert after.rng == before.rng and after.output == before.output
    assert after.ram[0x10:0x12] == before.ram[0x10:0x12]
    env.set_state(checkpoint)
    assert env.get_state() == checkpoint
    env.close()


def test_v4_truncated_saves_fail_without_mutating_state(tmp_path):
    path = tmp_path / "save.z4"
    path.write_bytes(save_story())
    storage = Storage()
    env = FernzEnv(path, seed=42, save_handler=storage.save, restore_handler=storage.restore)
    env.reset()
    env.step("save")
    original, before = storage.data, env.get_state()
    for size in range(len(original)):
        storage.data = original[:size]
        assert not env._machine._restore()
        assert env.get_state() == before
    env.close()


@pytest.mark.parametrize("opcode", (0xB5, 0xB6))
@pytest.mark.parametrize("failure", ("missing", "cancel", "os-error", "malformed"))
def test_v4_save_restore_failure_stores_zero(opcode, failure):
    def unavailable(*args):
        if failure == "os-error":
            raise OSError("unavailable")
        return False if opcode == 0xB5 else b"bad" if failure == "malformed" else None

    handler = None if failure == "missing" else unavailable
    io = HostIO(save=handler) if opcode == 0xB5 else HostIO(restore=handler)
    story = Story(program_bytes(bytes((opcode, 0x11)) + READ, version=4))
    m = Machine(Memory(story), io=io)
    m.run()
    assert m.read_variable(17) == 0
