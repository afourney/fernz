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
