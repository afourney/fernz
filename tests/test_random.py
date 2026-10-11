from random import Random

import pytest

from fernz import FernzEnv, Memory, Story
from fernz._machine import Machine
from fernz._random import RandomGenerator

from .observation_helpers import plain_text
from .random_story import random_story, results

# Values recorded from our synthetic story through Jericho 3.3.1 and Frotz
# 2.54/2.55 public interfaces. These are observations, not computed expectations.
VECTORS = (
    (1, 6, [1] * 12),
    (5, 6, [1, 2, 3, 4, 5, 1, 2, 3, 4, 5, 1, 2]),
    (5, 3, [1, 2, 3, 1, 2, 1, 2, 3, 1, 2, 1, 2]),
    (1000, 6, [2, 5, 6, 6, 1, 1, 5, 5, 6, 3, 3, 3]),
    (1234, 6, [1, 4, 3, 1, 3, 6, 3, 3, 6, 2, 2, 4]),
    (32767, 6, [5, 1, 2, 5, 4, 1, 5, 3, 1, 2, 1, 1]),
    (32768, 6, [3, 1, 6, 2, 4, 4, 5, 6, 4, 2, 1, 5]),
    (1000, 32767, [18626, 14063, 5796, 15162, 15601, 27361, 32063, 11255]),
)


@pytest.mark.parametrize("seed,bound,expected", VECTORS)
def test_observed_predictable_sequences(seed, bound, expected):
    rng = RandomGenerator()
    assert rng.random(-seed) == 0
    assert [rng.random(bound) for _ in expected] == expected
    assert rng.random(-seed) == 0
    assert [rng.random(bound) for _ in expected] == expected


@pytest.mark.parametrize("seed,bound,expected", VECTORS)
def test_machine_random_opcode_matches_observations(seed, bound, expected):
    operands = [-seed] + [bound] * len(expected)
    machine = Machine(Memory(Story(random_story(operands))))
    assert results(machine.run(), len(operands)) == [0, *expected]


def test_counting_boundary_and_changing_ranges():
    rng = RandomGenerator()
    rng.random(-999)
    assert [rng.random(32767) for _ in range(1002)] == [*range(1, 1000), 1, 2, 3]
    rng.random(-5)
    assert [rng.random(n) for n in (10, 1, 2, 10, 3, 10, 3)] == [1, 1, 1, 4, 2, 1, 2]


def test_range_one_still_advances_the_affine_generator():
    rng = RandomGenerator()
    rng.random(-1000)
    assert rng.random(1) == 1
    assert rng.random(32767) == 14063


def test_switching_between_both_predictable_modes_reseeds():
    rng = RandomGenerator()
    rng.random(-1000)
    assert rng.random(32767) == 18626
    rng.random(-5)
    assert [rng.random(10) for _ in range(7)] == [1, 2, 3, 4, 5, 1, 2]
    rng.random(-1000)
    assert rng.random(32767) == 18626
    rng.random(-5)
    assert rng.random(10) == 1


@pytest.mark.parametrize(
    "seed,expected",
    [(1, [347, 131, 10983]), (42, [14545, 24057, 29926]), (2147483647, [32422, 562, 22047])],
)
def test_positive_host_seed_and_random_zero_match_both_references(seed, expected):
    rng = RandomGenerator(seed)
    assert [rng.random(32767) for _ in expected] == expected
    rng.random(-5)
    assert rng.random(0) == 0
    assert [rng.random(32767) for _ in expected] == expected
    rng.reset()
    assert [rng.random(32767) for _ in expected] == expected


def test_explicit_zero_host_seed_is_deterministic_like_frotz_cli():
    # Jericho's constructor treats zero as automatic seeding instead; do not
    # conflate that host policy with the Z-machine's negative-seed contract.
    rng = RandomGenerator(0)
    assert [rng.random(32767) for _ in range(6)] == [1, 347, 131, 10983, 1091, 11657]
    rng.random(0)
    assert rng.random(32767) == 1


def test_automatic_seeding_uses_fresh_entropy_only_on_reseed(monkeypatch):
    seeds = iter((1000, 1234, 32768))
    requests = []

    def entropy(bits):
        requests.append(bits)
        return next(seeds)

    monkeypatch.setattr("fernz._random.secrets.randbits", entropy)
    rng = RandomGenerator()
    expected = Random(1000)
    assert [rng.random(6) for _ in range(3)] == [expected.randrange(1, 7) for _ in range(3)]
    assert rng.random(0) == 0
    assert rng.random(6) == Random(1234).randrange(1, 7)
    rng.random(-5)
    assert rng.random(6) == 1
    rng.reset()
    assert rng.random(6) == Random(32768).randrange(1, 7)
    assert requests == [256, 256, 256]


@pytest.mark.parametrize("bound", (1, 6, 20000, 32767))
def test_ordinary_mode_rejects_surplus_samples_instead_of_folding_them(monkeypatch, bound):
    # Supply two rejected bit patterns followed by the two valid endpoints.
    # A modulo mapping would accept the first two and advance the wrong amount.
    bits = bound.bit_length()
    samples = iter(((1 << bits) - 1, bound, 0, bound - 1))
    requests = []

    class ControlledRandom(Random):
        def getrandbits(self, count):
            requests.append(count)
            return next(samples)

    monkeypatch.setattr("fernz._random.Random", ControlledRandom)
    rng = RandomGenerator()
    assert [rng.random(bound), rng.random(bound)] == [1, bound]
    assert requests == [bits] * 4


@pytest.mark.parametrize("seed", (0, 5, 1000))
def test_explicit_seeding_keeps_only_compact_compatibility_state(monkeypatch, seed):
    def unexpected(*args):
        pytest.fail("Predictable mode must not allocate a Python RNG or request entropy")

    monkeypatch.setattr("fernz._random.Random", unexpected)
    monkeypatch.setattr("fernz._random.secrets.randbits", unexpected)
    rng = RandomGenerator(seed)
    assert rng.get_state().python_state is None
    rng.random(6)
    rng.random(0)
    assert rng.get_state().python_state is None


@pytest.mark.parametrize("seed", (5, 1000))
def test_opcode_seed_leaves_python_mode_until_random_zero(monkeypatch, seed):
    monkeypatch.setattr("fernz._random.secrets.randbits", lambda bits: 42)
    rng = RandomGenerator()
    assert rng.get_state().python_state is not None
    rng.random(-seed)
    assert rng.get_state().host_seed is None
    assert rng.get_state().python_state is None
    expected = RandomGenerator(0)
    expected.random(-seed)
    assert [rng.random(6) for _ in range(20)] == [expected.random(6) for _ in range(20)]
    rng.random(0)
    assert rng.get_state().python_state == Random(42).getstate()


def test_environment_reset_restores_host_seed_and_owns_its_rng(tmp_path):
    game = tmp_path / "rng.z3"
    game.write_bytes(random_story([32767, -5, 10, 10, 0, 32767]))
    first = FernzEnv(game, seed=42)
    other = FernzEnv(game, seed=1)
    for _ in range(2):
        assert results(plain_text(first.reset()[0]), 6) == [14545, 0, 1, 2, 0, 14545]
        assert results(plain_text(other.reset()[0]), 6) == [347, 0, 1, 2, 0, 347]


@pytest.mark.parametrize("seed", (-1, 2**31, 2**40))
def test_host_seed_limits(seed):
    with pytest.raises(ValueError, match="Host seed"):
        RandomGenerator(seed)


@pytest.mark.parametrize("operand", (-32769, 32768))
def test_operand_limits(operand):
    with pytest.raises(ValueError, match="signed 16-bit"):
        RandomGenerator().random(operand)


def test_seed_and_operand_must_be_integers():
    with pytest.raises(TypeError):
        RandomGenerator(1.5)
    with pytest.raises(TypeError):
        RandomGenerator().random(1.5)
