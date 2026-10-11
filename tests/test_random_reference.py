"""Compare synthetic RNG probes through public APIs and a Frotz executable only."""

import subprocess
import warnings

import pytest

from fernz import FernzEnv, Story
from fernz._random import RandomGenerator

from .observation_helpers import plain_text
from .random_story import random_story, results

pytestmark = pytest.mark.reference

VERSIONS = (3, 4, 5, 8)
RANGES = [1, 2, 3, 6, 10, 255, 256, 1000, 32766, 32767]


def frotz_results(executable, story, operands, seed):
    # A quit-terminated probe avoids input/status-line screen redraws. No game
    # files, interpreter internals, source inspection, or compiler are involved.
    completed = subprocess.run(
        [executable, "-q", "-m", "-p", "-s", str(seed), str(story)],
        input="",
        text=True,
        capture_output=True,
        timeout=15,
        check=True,
    )
    assert completed.stderr == ""
    return results(completed.stdout, len(operands))


def jericho_results(story, operands, seed):
    from jericho import FrotzEnv

    # Synthetic stories deliberately have no Jericho-specific game bindings.
    # Score/move hooks are irrelevant: all results come from printed opcodes.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="Game .* is not fully supported", category=UserWarning
        )
        env = FrotzEnv(str(story), seed=seed)
    try:
        initial = results(plain_text(env.reset()[0]), len(operands))
        assert results(plain_text(env.reset()[0]), len(operands)) == initial
        return initial
    finally:
        env.close()


def compare(tmp_path, dfrotz, operands, version, seed=42):
    story = tmp_path / f"random.z{version}"
    story.write_bytes(random_story(operands, version))
    assert Story.from_file(story).verify_checksum() is True
    expected = frotz_results(dfrotz, story, operands, seed)
    assert jericho_results(story, operands, seed) == expected
    rng = RandomGenerator(seed)
    assert [rng.random(operand) for operand in operands] == expected
    env = FernzEnv(story, seed=seed)
    try:
        for _ in range(2):
            assert results(plain_text(env.reset()[0]), len(operands)) == expected
    finally:
        env.close()
    return expected


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("seed", (1, 5, 42, 999, 1000, 1001, 1234, 32767, 32768))
def test_opcode_seed_sequences(tmp_path, dfrotz, version, seed):
    # Cross the longest counting cycle and exercise both large and small ranges.
    compare(tmp_path, dfrotz, [-seed] + RANGES * 102, version)


@pytest.mark.parametrize("version", VERSIONS)
def test_mode_switches_and_reseeding(tmp_path, dfrotz, version):
    operands = [-5] + [3] * 8 + [-1000] + [6] * 12 + [-999] + [32767] * 1002
    operands += [-1000] + [6] * 12 + [-1, 32767, -5] + [10] * 8
    compare(tmp_path, dfrotz, operands, version)


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("seed", (1, 5, 999, 1000, 32768, 2147483647))
def test_host_seeds_and_random_zero(tmp_path, dfrotz, version, seed):
    operands = RANGES * 12 + [-5] + RANGES * 2 + [0] + RANGES * 12
    observed = compare(tmp_path, dfrotz, operands, version, seed)
    assert observed[:120] == observed[-120:]


@pytest.mark.parametrize("version", VERSIONS)
def test_explicit_zero_host_seed_matches_frotz(tmp_path, dfrotz, version):
    # Jericho seed=0 requests automatic seeding. An explicit Fernz seed=0 stays
    # reproducible and follows dfrotz -s 0, so no three-way equality is claimed.
    operands = RANGES * 20 + [-5, 10, 0] + RANGES * 20
    story = tmp_path / f"zero.z{version}"
    story.write_bytes(random_story(operands, version))
    expected = frotz_results(dfrotz, story, operands, 0)
    rng = RandomGenerator(0)
    assert [rng.random(operand) for operand in operands] == expected


def test_parameters_against_independent_seed_sweep(tmp_path, dfrotz):
    # Use a different measurement from sequence tests: independently seed two
    # draws at adjacent seeds, plus seeds spanning the entire opcode seed range.
    seeds = [*range(1000, 1128), 1234, 2048, 4096, 8192, 16384, 32767, 32768]
    operands = [operand for seed in seeds for operand in (-seed, 32767, 32767)]
    compare(tmp_path, dfrotz, operands, 3)
