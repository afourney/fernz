from dataclasses import FrozenInstanceError, replace
from random import Random

import pytest

from fernz import ExecutionError, FernzEnv, GameState
from fernz._random import RandomGenerator

from .observation_helpers import plain_text, text_response
from .story_files import READ, program_bytes


@pytest.fixture
def game(tmp_path):
    # Suspend inside two nested calls. Each frame has its own stack; both
    # routines have locals. On input, unwind with a random result as the score,
    # print values from every frame, then suspend again in the initial frame.
    root = bytes.fromhex("e8 7f 0b e0 1f 03 00 07 11 e6 bf 00 bb") + READ + b"\xba"
    outer = bytes.fromhex("01 00 03 e8 7f 16 e0 3f 03 40 01 e6 bf 01 bb e6 bf 00 bb ab 01")
    inner = (
        bytes.fromhex("01 00 09 e8 7f 21")
        + READ
        + bytes.fromhex("e6 bf 01 bb e6 bf 00 bb e7 3f 7f ff 01 e6 bf 01 bb ab 01")
    )
    path = tmp_path / "snapshot.z3"
    path.write_bytes(program_bytes(root, (0x600, outer), (0x680, inner)))
    return path


def test_snapshot_is_detached_immutable_and_contains_dynamic_memory(game):
    env = FernzEnv(game, seed=42)
    with pytest.raises(RuntimeError, match="reset"):
        env.get_state()
    env.reset()
    state = env.get_state()
    assert isinstance(state, GameState)
    assert len(state.ram) == env.story.header.static_memory == 0x300
    assert state.ram == env.memory.read_bytes(0, 0x300)
    assert [f.stack for f in state.frames] == [(11,), (22,), (33,)]
    assert [f.locals for f in state.frames] == [(), (7,), (9,)]
    assert [f.argument_count for f in state.frames] == [0, 1, 0]
    assert state.input_request.text == 0x280
    assert state.input_request.parse == 0x2A0
    assert state.input_request.instruction_address == state.pc - len(READ)
    assert env.get_state() == state
    with pytest.raises(FrozenInstanceError):
        state.pc = 0
    with pytest.raises(TypeError):
        state.ram[0x250] = 1
    with pytest.raises(TypeError):
        state.frames[1].stack[0] = 99
    with pytest.raises(FrozenInstanceError):
        state.rng.position = 1
    env.memory.write_byte(0x250, 1)
    assert state.ram[0x250] == 0


def test_restore_replays_nested_calls_randomness_score_and_quit(game):
    env = FernzEnv(game, seed=42)
    opening = env.reset()
    memory = env.memory
    state = env.get_state()
    expected = ("\n9\n33\n14545\n14545\n22\n11\n", 14545, False, {"score": 14545, "moves": 0})
    for _ in range(3):
        assert env.set_state(state) is None
        assert env.memory is memory
        assert env.get_state() == state
        assert not env.done
        assert text_response(env.step("LOOK")) == expected
        assert len(env.get_state().frames) == 1
        assert env.step("quit")[2] is True
        ending = env.get_state()
        assert ending.halted and ending.input_request is None
    assert env.reset() == opening
    env.set_state(ending)
    assert env.done
    with pytest.raises(RuntimeError, match="reset"):
        env.step("look")
    env.set_state(state)
    assert text_response(env.step("LOOK")) == expected


def test_snapshot_can_fork_into_same_story_without_shared_mutable_state(game, tmp_path):
    env = FernzEnv(game, seed=42)
    env.reset()
    state = env.get_state()
    # A different filename and file padding do not change the addressable story.
    copy = tmp_path / "copy.z3"
    copy.write_bytes(game.read_bytes() + b"padding")
    other = FernzEnv(copy, seed=7)
    other.set_state(state)  # No reset required; no instructions executed here.
    assert other.get_state() == state
    expected = env.step("look")
    assert other.get_state() == state
    assert other.step("look") == expected
    other.memory.write_byte(0x250, 77)
    assert env.memory.read_byte(0x250) == 0
    # Host seed policy is part of the checkpoint, including subsequent resets.
    other.reset()
    assert other.get_state() == state


def test_different_story_is_rejected_without_changing_current_game(game, tmp_path):
    env = FernzEnv(game, seed=42)
    env.reset()
    state = env.get_state()
    data = bytearray(game.read_bytes())
    data[-1] = 1  # Same version, release, serial, and header checksum; different image.
    path = tmp_path / "other.z3"
    path.write_bytes(data)
    other = FernzEnv(path, seed=99)
    other.reset()
    before = other.get_state()
    with pytest.raises(ValueError, match="different story"):
        other.set_state(state)
    assert other.get_state() == before


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda s: None,
        lambda s: (s.ram, s.frames, s.pc),
        lambda s: replace(s, format_version=1),
        lambda s: replace(s, format_version=3),
        lambda s: replace(s, ram=s.ram[:-1]),
        lambda s: replace(s, ram=bytearray(s.ram)),
        lambda s: replace(s, ram=s.ram[:14] + b"\x03\x01" + s.ram[16:]),
        lambda s: replace(s, pc=-1),
        lambda s: replace(s, pc=4097),
        lambda s: replace(s, frames=()),
        lambda s: replace(s, frames=list(s.frames)),
        lambda s: replace(s, frames=(replace(s.frames[0], locals=(1,)),)),
        lambda s: replace(s, frames=(s.frames[0], replace(s.frames[1], locals=(0,) * 16))),
        lambda s: replace(s, frames=(replace(s.frames[0], stack=(65536,)),)),
        lambda s: replace(s, frames=(s.frames[0], replace(s.frames[1], stack=[1]))),
        lambda s: replace(s, frames=(s.frames[0], replace(s.frames[1], return_address=None))),
        lambda s: replace(s, frames=(s.frames[0], replace(s.frames[1], store=256))),
        lambda s: replace(s, frames=(s.frames[0], replace(s.frames[1], argument_count=4))),
        lambda s: replace(s, rng=replace(s.rng, host_seed=-1)),
        lambda s: replace(s, rng=replace(s.rng, state=2**31)),
        lambda s: replace(s, rng=replace(s.rng, period=1000)),
        lambda s: replace(s, rng=replace(s.rng, period=5, position=5)),
        lambda s: replace(s, rng=replace(s.rng, position=1)),
        lambda s: replace(s, screen_enabled=1),
        lambda s: replace(s, halted=True),
        lambda s: replace(s, game_over=1),
        lambda s: replace(s, victory=None),
        lambda s: replace(s, input_request=None),
        lambda s: replace(s, input_request=replace(s.input_request, text=-1)),
        lambda s: replace(s, input_request=replace(s.input_request, instruction_address=-1)),
    ],
)
def test_invalid_restore_is_atomic(game, corrupt):
    env = FernzEnv(game, seed=42)
    env.reset()
    old = env.get_state()
    env.step("look")
    before = env.get_state()
    memory = env.memory
    with pytest.raises((TypeError, ValueError)):
        env.set_state(corrupt(old))
    assert env.get_state() == before
    assert env.memory is memory
    assert env.step("quit")[2] is True


def test_restore_recovers_after_execution_failure(game):
    env = FernzEnv(game, seed=42)
    env.reset()
    state = env.get_state()
    with pytest.raises(ExecutionError, match="budget"):
        env.step("look", max_steps=1)
    with pytest.raises(RuntimeError, match="reset"):
        env.get_state()
    env.set_state(state)
    assert env.get_state() == state
    assert env.step("look")[1] == 14545


def test_restore_preserves_output_selection_header_flags_and_no_old_output(tmp_path):
    game = tmp_path / "output.z3"
    # Print A, disable screen, read; reenable, print B, read; quit.
    game.write_bytes(
        program_bytes(
            bytes.fromhex("e5 7f 41 f3 3f ff ff")
            + READ
            + bytes.fromhex("f3 7f 01 e5 7f 42")
            + READ
            + b"\xba"
        )
    )
    env = FernzEnv(game)
    assert plain_text(env.reset()[0]) == "A"
    env.memory.write_byte(0x11, 3)
    saved = env.get_state()
    assert not saved.screen_enabled
    assert plain_text(env.step("look")[0]) == "B"  # Enter happened while output was disabled.
    env.memory.write_byte(0x11, 0)
    env.set_state(saved)
    assert env.memory.read_byte(0x11) == 2  # Fixed font survives; no transcript is available.
    assert plain_text(env.step("look")[0]) == "B"  # Neither old A nor old B is replayed.


@pytest.mark.parametrize("operand", (None, -5, -1000))
@pytest.mark.parametrize("host_seed", (None, 42))
def test_random_snapshot_restores_each_mode_without_drawing_entropy(
    monkeypatch, operand, host_seed
):
    rng = RandomGenerator(host_seed)
    if operand is not None:
        rng.random(operand)
    for _ in range(3):
        rng.random(10)
    state = rng.get_state()
    expected = [rng.random(n) for n in (10, 32767, 3, 6) * 5]

    def unexpected_entropy(bits):
        pytest.fail("Restoring RNG state must not request entropy")

    monkeypatch.setattr("fernz._random.secrets.randbits", unexpected_entropy)
    restored = RandomGenerator.from_state(state)
    assert restored.get_state() == state
    assert [restored.random(n) for n in (10, 32767, 3, 6) * 5] == expected
    if host_seed is not None:
        restored.random(0)
        fresh = RandomGenerator(host_seed)
        assert restored.random(32767) == fresh.random(32767)


@pytest.mark.parametrize("version", (3, 5))
def test_python_rng_checkpoint_replays_and_forks_across_environments(
    tmp_path, version, monkeypatch
):
    read = READ + (b"\x10" if version == 5 else b"")
    draw = bytes.fromhex("e7 3f 7f ff 00 e6 bf 00")
    path = tmp_path / f"random.z{version}"
    path.write_bytes(program_bytes(read + draw + read + draw + read, version=version))
    env = FernzEnv(path)
    env.reset()
    saved = env.get_state()
    assert saved.format_version == 5
    assert saved.rng.python_state is not None
    recipient = FernzEnv(path, seed=42)

    def unexpected(*args):
        pytest.fail("Checkpoint restoration and copying must not request entropy")

    monkeypatch.setattr("fernz._random.secrets.randbits", unexpected)
    recipient.set_state(saved)
    fork = env.copy()
    first = env.step("look")
    after_first = env.get_state()
    second = env.step("look")
    after_second = env.get_state()
    for candidate in (recipient, fork, env):
        candidate.set_state(saved)
        assert candidate.step("look") == first
        assert candidate.get_state() == after_first
        assert candidate.step("look") == second
        assert candidate.get_state() == after_second


@pytest.mark.parametrize(
    "changes",
    [
        {"python_state": [3, Random(0).getstate()[1], None]},
        {"python_state": (2, Random(0).getstate()[1], None)},
        {"python_state": (3, [0] * 625, None)},
        {"python_state": (3, (0,) * 624, None)},
        {"python_state": (3, (-1,) + (0,) * 624, None)},
        {"python_state": (3, (2**32,) + (0,) * 624, None)},
        {"python_state": (3, (0,) * 624 + (625,), None)},
        {"python_state": (3, Random(0).getstate()[1], 0.0)},
        {"host_seed": 42},
        {"state": 42},
        {"period": 5},
    ],
)
def test_invalid_python_rng_checkpoint_is_rejected_atomically(game, changes):
    env = FernzEnv(game)
    env.reset()
    before = env.get_state()
    with pytest.raises((TypeError, ValueError)):
        env.set_state(replace(before, rng=replace(before.rng, **changes)))
    assert env.get_state() == before


def test_legacy_schema_four_keeps_affine_sequence_until_next_reseed(game, monkeypatch):
    # Old unseeded snapshots contain a compact affine state, not Python state.
    env = FernzEnv(game, seed=42)
    env.reset()
    legacy = replace(env.get_state(), format_version=4)
    legacy = replace(legacy, rng=replace(legacy.rng, host_seed=None))
    expected = env.step("look")
    env.set_state(legacy)
    assert env.get_state().format_version == 5
    assert env.get_state().rng.python_state is None
    assert env.step("look") == expected
    monkeypatch.setattr("fernz._random.secrets.randbits", lambda bits: 1000)
    env.reset()
    assert env.get_state().rng.python_state == Random(1000).getstate()
    with pytest.raises(ValueError, match="schema 5"):
        env.set_state(replace(env.get_state(), format_version=4))
