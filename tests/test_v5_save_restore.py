"""V5/V8 store-form Quetzal continuations and atomic restore failures."""

from dataclasses import replace

import pytest

from fernz import FernzEnv, Memory, Story, UnsupportedOpcodeError
from fernz._host_io import HostIO
from fernz._machine import Machine
from fernz._quetzal import SavedGame, dumps, loads
from fernz._random import RandomGenerator
from fernz._state import FrameState

from .observation_helpers import plain_text
from .story_files import READ, program_bytes
from .test_save_restore import Storage
from .v5_story import save_story


@pytest.mark.parametrize("store", (0, 8))
@pytest.mark.parametrize("high", (False, True))
@pytest.mark.parametrize("version", (5, 8))
def test_v5_save_resume_result_and_discarding_seven_argument_frame(tmp_path, store, high, version):
    path = tmp_path / f"save.z{version}"
    path.write_bytes(save_story(store=store, high=high, version=version))
    storage = Storage()
    first = FernzEnv(path, seed=42, save_handler=storage.save)
    first.reset()
    assert plain_text(first.step("save")[0]) == "\n1\n"
    saved = loads(first.story, storage.data)
    assert saved.frames[1].store is None
    assert saved.frames[1].argument_count == 7
    assert saved.frames[1].locals[:7] == tuple(range(1, 8))
    assert saved.frames[1].stack == (0x2222,)
    assert first.memory.read_byte(saved.pc) == store
    assert (saved.pc > (0x3FFFF if version == 8 else 0xFFFF)) is high
    expected = first.step("continue")
    assert expected[0].text == "\n8738\n77\n"
    second = FernzEnv(path, seed=42, restore_handler=storage.restore)
    second.reset()
    assert plain_text(second.step("restore")[0]) == "\n2\n"
    assert second.step("continue") == expected


@pytest.mark.parametrize("version", (5, 8))
def test_v5_restore_preserves_rng_output_and_flags_while_snapshots_restore_them(tmp_path, version):
    path = tmp_path / f"save.z{version}"
    path.write_bytes(save_story(version=version))
    storage = Storage()
    env = FernzEnv(path, seed=42, save_handler=storage.save, restore_handler=storage.restore)
    env.reset()
    env.step("save")
    saved_checkpoint = env.get_state()
    env.reset()
    rng = RandomGenerator(1000)
    rng.random(100)
    env.set_state(replace(env.get_state(), rng=rng.get_state(), screen_enabled=False))
    env.memory.write_byte(0x11, env.memory.read_byte(0x11) | 3)
    before = env.get_state()
    assert plain_text(env.step("restore")[0]) == ""
    after = env.get_state()
    assert after.rng == before.rng and after.output == before.output
    assert after.ram[0x10:0x12] == before.ram[0x10:0x12]
    env.set_state(saved_checkpoint)
    assert env.get_state() == saved_checkpoint


@pytest.mark.parametrize("version", (5, 8))
def test_v5_bad_files_fail_without_mutating_live_state(tmp_path, version):
    path = tmp_path / f"save.z{version}"
    path.write_bytes(save_story(version=version))
    storage = Storage()
    env = FernzEnv(path, seed=42, save_handler=storage.save, restore_handler=storage.restore)
    env.reset()
    env.step("save")
    original = storage.data
    before = env.get_state()
    for length in range(len(original)):
        storage.data = original[:length]
        assert not env._machine._restore()
        assert env.get_state() == before
    saved = loads(env.story, original)
    for pc in (env.story.size - 1, 0x280):
        # Both bytes name local variables absent from the initial caller.
        malformed = SavedGame(saved.ram, (FrameState((), (), None, None),), pc)
        if pc == 0x280:
            ram = bytearray(malformed.ram)
            ram[pc] = 15
            malformed = replace(malformed, ram=bytes(ram))
        storage.data = dumps(env.story, malformed)
        assert not env._machine._restore()
        assert env.get_state() == before


@pytest.mark.parametrize("opcode", (0, 1))
@pytest.mark.parametrize("failure", ("missing", "cancel", "os-error", "malformed"))
@pytest.mark.parametrize("version", (5, 8))
def test_v5_save_restore_failures_store_zero(opcode, failure, version):
    def unavailable(*args):
        if failure == "os-error":
            raise OSError("unavailable")
        return False if opcode == 0 else b"bad" if failure == "malformed" else None

    handler = None if failure == "missing" else unavailable
    io = HostIO(save=handler) if opcode == 0 else HostIO(restore=handler)
    code = bytes((0xBE, opcode, 0xFF, 0x11)) + READ + b"\x10"
    m = Machine(Memory(Story(program_bytes(code, version=version))), io=io)
    m.run()
    assert m.read_variable(17) == 0


@pytest.mark.parametrize("opcode", (0, 1))
@pytest.mark.parametrize("version", (5, 8))
def test_auxiliary_region_io_is_explicitly_unsupported(opcode, version):
    code = bytes((0xBE, opcode, 0x5F, 0x40, 1, 0x10))
    m = Machine(Memory(Story(program_bytes(code, version=version))))
    with pytest.raises(UnsupportedOpcodeError, match="Auxiliary"):
        m.run()
