"""V5 execution compared through Jericho's documented public Python API."""

import pytest

from fernz import FernzEnv

from .v5_cases import SEED_905, STARTUP_ACTIONS, STORY_905
from .v5_vectors import capture_reference, check_step
from .vector_archive import digest

pytestmark = pytest.mark.reference


@pytest.mark.smoke
def test_905_first_commands_match_live_reference(jericho_games):
    from jericho import FrotzEnv

    path = jericho_games / STORY_905["filename"]
    assert digest(path.read_bytes()) == STORY_905["file_sha256"]
    reference = FrotzEnv(str(path), seed=SEED_905)
    env = FernzEnv(path, seed=SEED_905)
    try:
        check_step(env, capture_reference(reference, None, reference.reset()[0]))
        for action in STARTUP_ACTIONS:
            before, native = env.get_state(), reference.get_state()
            record = capture_reference(reference, action, reference.step(action)[0])
            check_step(env, record)
            expected = env.get_state()
            env.set_state(before)
            reference.set_state(native)
            assert capture_reference(reference, action, reference.step(action)[0]) == record
            check_step(env, record)
            assert env.get_state() == expected
    finally:
        env.close()
        reference.close()


def test_905_full_route_detours_endings_and_persistence(jericho_games):
    from .scripts.v5_game_vectors import generate_905
    from .v5_vectors import replay_documents

    path = jericho_games / STORY_905["filename"]
    replay_documents(path, generate_905(path))


def test_905_public_copies_branch_without_advancing_the_original(jericho_games):
    from jericho import FrotzEnv

    from .v5_queries import query_fingerprint
    from .v5_vectors import measure_step

    path = jericho_games / STORY_905["filename"]
    reference = FrotzEnv(str(path), seed=SEED_905)
    env = FernzEnv(path, seed=SEED_905)
    environments = [reference, env]
    try:
        check_step(env, capture_reference(reference, None, reference.reset()[0]))
        route = reference.get_walkthrough()
        for action in route[:11]:
            check_step(env, measure_step(reference, action))
        before = env.get_state()
        native_before = query_fingerprint(reference)
        fork, native_fork = env.copy(), reference.copy()
        environments += [fork, native_fork]
        for action in route[11:]:
            check_step(fork, measure_step(native_fork, action))
        assert fork.victory() and fork.get_score() == 1 and not fork.done
        assert env.get_state() == before
        assert query_fingerprint(reference) == native_before
        for action in ("open wallet", "look", "inventory"):
            check_step(env, measure_step(reference, action))
        winning_state = fork.get_state()
        env.set_state(winning_state)
        assert query_fingerprint(env, fernz=True) == query_fingerprint(native_fork)
        assert env.copy().get_state() == winning_state
    finally:
        for candidate in environments:
            candidate.close()


@pytest.mark.parametrize("value", (0, 544, 545, 600, 1440, 65535))
def test_905_move_counter_mapping_uses_public_snapshot_measurements(jericho_games, value):
    from jericho import FrotzEnv

    path = jericho_games / STORY_905["filename"]
    reference = FrotzEnv(str(path), seed=SEED_905)
    env = FernzEnv(path, seed=SEED_905)
    try:
        reference.reset()
        env.reset()
        native = reference.get_state()
        ram = native[0].copy()
        address = int.from_bytes(ram[12:14].tobytes(), "big") + 34
        ram[address : address + 2] = list(value.to_bytes(2, "big"))
        reference.set_state((ram, *native[1:]))
        env.memory.write_word(address, value)
        assert env.get_moves() == reference.get_moves() == value - 545
    finally:
        env.close()
        reference.close()
