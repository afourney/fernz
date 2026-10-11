"""Environment forks, deferred host seeding, and live V3 status queries."""

from random import Random

import pytest

from fernz import ExecutionError, FernzEnv

from .environment_story import seed_story
from .observation_helpers import plain_text
from .story_files import READ, program_bytes, put_word, story_bytes
from .test_save_restore import Storage, results
from .test_state import game as game


@pytest.fixture(params=(3, 5))
def seeds(tmp_path, request):
    path = tmp_path / f"seeds.z{request.param}"
    path.write_bytes(seed_story(request.param))
    return path


def test_copy_forks_nested_execution_without_io_entropy_or_shared_memory(game, monkeypatch):
    monkeypatch.setattr("fernz._random.secrets.randbits", lambda bits: 42)
    env = FernzEnv(game)
    env.reset()
    state = env.get_state()
    game.unlink()  # An initialized environment must not need its original file.

    def forbidden(bits):
        pytest.fail("Copying must not request entropy")

    monkeypatch.setattr("fernz._random.secrets.randbits", forbidden)
    other = env.copy()
    assert other is not env
    assert other.story is env.story
    assert other.memory is not env.memory
    assert other.get_state() == state
    env.memory.write_byte(0x250, 77)
    assert other.memory.read_byte(0x250) == 0
    expected = env.step("look")
    assert other.get_state() == state  # All three stacks and RNG remain untouched.
    assert other.step("look") == expected
    assert other.step("quit")[2] is True
    assert not env.done
    assert env.step("quit")[2] is True
    halted = other.copy()
    assert halted.done and halted.get_state() == other.get_state()
    assert halted.get_score() == other.get_score() == Random(42).randrange(1, 32768)
    assert halted.get_moves() == other.get_moves() == 0


@pytest.mark.parametrize("version", [1, 3, 5, 8])
def test_copy_before_reset_preserves_loaded_memory_and_initialization(version, tmp_path):
    path = tmp_path / "loaded.z"
    path.write_bytes(story_bytes(version))
    env = FernzEnv(path, seed=42)
    env.memory.write_byte(0x250, 77)
    path.unlink()
    other = env.copy()
    assert other.memory.read_bytes(0, len(other.memory)) == env.memory.read_bytes(
        0, len(env.memory)
    )
    other.memory.write_byte(0x250, 88)
    assert env.memory.read_byte(0x250) == 77
    for query in (other.get_state, other.get_score, other.get_moves):
        with pytest.raises(RuntimeError, match="reset"):
            query()
    assert not other.done


def test_copy_after_execution_failure_still_requires_reset_or_state(tmp_path):
    path = tmp_path / "failure.z3"
    path.write_bytes(program_bytes(READ + bytes.fromhex("e5 7f 41") + READ))
    env = FernzEnv(path, seed=42)
    env.reset()
    saved = env.get_state()
    with pytest.raises(ExecutionError, match="budget"):
        env.step("look", max_steps=1)
    other = env.copy()
    for query in (other.get_state, other.get_score, other.get_moves, env.get_score, env.get_moves):
        with pytest.raises(RuntimeError, match="reset"):
            query()
    other.set_state(saved)
    assert plain_text(other.step("look")[0]) == "\nA"
    with pytest.raises(RuntimeError, match="reset"):
        env.get_state()


def test_copy_retains_host_callback_references_but_not_vm_mutations(tmp_path):
    path = tmp_path / "callbacks.z3"
    path.write_bytes(
        program_bytes(READ + bytes.fromhex("b5 c2 e5 7f 53") + READ + bytes.fromhex("b6 c2 ba"))
    )
    storage, emitted = Storage(), []
    env = FernzEnv(
        path,
        save_handler=storage.save,
        restore_handler=storage.restore,
        output_handler=emitted.append,
    )
    env.reset()
    state = env.get_state()
    other = env.copy()
    assert emitted == []
    assert plain_text(other.step("save")[0]) == "\nS"
    assert "".join(emitted) == "\nS"
    assert storage.saves == 1 and storage.data.startswith(b"FORM")
    assert env.get_state() == state
    emitted.clear()
    assert plain_text(other.step("restore")[0]) == "\nS"
    assert "".join(emitted) == "\nS"
    assert storage.restores == 1
    assert env.get_state() == state


def test_seed_is_deferred_until_host_reset_and_copy_retains_both_policies(seeds):
    env = FernzEnv(seeds, seed=42)
    assert results(plain_text(env.reset()[0])) == [14545]
    saved = env.get_state()
    assert env.seed(1000) == 1000
    assert env.get_state() == saved
    other = env.copy()
    for candidate in (env, other):
        assert results(plain_text(candidate.step("next")[0])) == [24057]
        assert results(plain_text(candidate.step("random zero")[0])) == [14545]
        assert results(plain_text(candidate.step("restart")[0])) == [14545]
        assert results(plain_text(candidate.reset()[0])) == [18626]
        assert candidate.get_state().rng.host_seed == 1000
    other.seed(1)
    assert results(plain_text(other.reset()[0])) == [347]
    assert results(plain_text(env.reset()[0])) == [18626]
    env.set_state(saved)
    assert results(plain_text(env.reset()[0])) == [14545]  # Existing checkpoint seed contract.


@pytest.mark.parametrize("explicit", [False, True])
def test_seed_none_selects_entropy_only_at_reset(seeds, monkeypatch, explicit):
    entropy = iter([42, 1000])
    requests = []

    def draw(bits):
        requests.append(bits)
        return next(entropy)

    monkeypatch.setattr("fernz._random.secrets.randbits", draw)
    env = FernzEnv(seeds, seed=42)
    env.reset()
    saved = env.get_state()
    assert (env.seed(None) if explicit else env.seed()) is None
    other = env.copy()
    assert env.get_state() == other.get_state() == saved
    assert requests == []
    assert results(plain_text(other.reset()[0])) == [Random(42).randrange(1, 32768)]
    assert results(plain_text(env.reset()[0])) == [Random(1000).randrange(1, 32768)]
    assert requests == [256, 256]


@pytest.mark.parametrize(
    "value,error", [(-1, ValueError), (2**31, ValueError), (1.5, TypeError), ("42", TypeError)]
)
def test_invalid_seed_is_rejected_without_changing_current_or_pending_state(seeds, value, error):
    with pytest.raises(error):
        FernzEnv(seeds, seed=value)
    env = FernzEnv(seeds, seed=42)
    env.reset()
    state = env.get_state()
    env.seed(1000)
    with pytest.raises(error):
        env.seed(value)
    assert env.get_state() == state
    assert results(plain_text(env.reset()[0])) == [18626]


@pytest.mark.parametrize("seed,first", [(0, 1), (2**31 - 1, 32422)])
def test_seed_accepts_boundaries_and_can_be_set_before_initialization(seeds, seed, first):
    env = FernzEnv(seeds)
    assert env.seed(seed) == seed
    assert results(plain_text(env.reset()[0])) == [first]


def test_seed_normalizes_integer_protocol_values(seeds):
    class Seed:
        def __index__(self):
            return 42

    env = FernzEnv(seeds, seed=Seed())
    assert results(plain_text(env.reset()[0])) == [14545]
    assert type(env.seed(Seed())) is int
    assert results(plain_text(env.reset()[0])) == [14545]


def test_score_and_moves_read_live_status_without_advancing_execution(tmp_path):
    path = tmp_path / "status.z3"
    path.write_bytes(
        program_bytes(
            READ + bytes.fromhex("cd 4f 11 80 00 0d 12 00 ba"), (0x102, b"\xff\xff\xff\xff")
        )
    )
    emitted = []
    env = FernzEnv(path, output_handler=emitted.append)
    for query in (env.get_score, env.get_moves):
        with pytest.raises(RuntimeError, match="reset"):
            query()
    assert env.reset()[1] == {"score": -1, "moves": 65535}
    saved = env.get_state()
    assert type(env.get_score()) is type(env.get_moves()) is int
    assert (env.get_score(), env.get_moves()) == (-1, 65535)
    assert env.get_state() == saved and emitted == []
    env.memory.write_word(0x102, 123)
    assert env.get_score() == 123
    _, _, done, info = env.step("quit")
    assert done and info == {"score": -32768, "moves": 0}
    assert (env.get_score(), env.get_moves()) == (-32768, 0)
    env.set_state(saved)
    assert (env.get_score(), env.get_moves()) == (-1, 65535)
    env.reset()
    assert (env.get_score(), env.get_moves()) == (-1, 65535)


def test_time_status_is_not_exposed_as_score_or_moves(tmp_path):
    data = bytearray(program_bytes(READ + b"\xba"))
    data[1] |= 2
    put_word(data, 0x102, 23)
    put_word(data, 0x104, 59)
    path = tmp_path / "time.z3"
    path.write_bytes(data)
    env = FernzEnv(path)
    assert env.reset()[1] == {"hours": 23, "minutes": 59}
    for query in (env.get_score, env.get_moves):
        with pytest.raises(NotImplementedError, match="time games"):
            query()
    assert env.step("quit")[3] == {"hours": 23, "minutes": 59}
