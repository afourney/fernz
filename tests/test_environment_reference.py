"""Environment helper comparisons through documented public Jericho calls."""

import warnings

import pytest

from fernz import FernzEnv

from .environment_story import seed_story
from .observation_helpers import plain_text
from .test_reference import assert_zork_step
from .test_reference import walkthrough_trace as walkthrough_trace
from .test_reference import zork1 as zork1
from .test_restart_reference import synthetic_reference
from .test_save_restore import Storage, results

pytestmark = pytest.mark.reference


def test_reference_zero_selects_the_games_recommended_seed(zork1):
    from jericho import FrotzEnv

    reference = FrotzEnv(str(zork1), seed=42)
    try:
        assert reference.seed(0) == 12
        first = reference.reset()
        assert reference.reset() == first
        # Other retained games recommend zero itself. Their complete live
        # walkthroughs verify that deterministic zero sequence independently.
        env = FernzEnv(zork1, seed=0)
        assert env.seed(0) == 0  # Fernz keeps explicit zero, as documented.
    finally:
        reference.close()


@pytest.mark.smoke
@pytest.mark.parametrize("version", (3, 5))
def test_seed_is_deferred_and_copy_preserves_fernz_active_host_policy(tmp_path, version):
    story = tmp_path / f"seeds.z{version}"
    story.write_bytes(seed_story(version))
    env = FernzEnv(story, seed=42)
    reference = synthetic_reference(story, 42)
    environments = [env, reference]
    try:
        for candidate in environments:
            assert results(plain_text(candidate.reset()[0])) == [14545]
            assert candidate.seed(1000) == 1000
        environments.append(env.copy())
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message="Game .* is not fully supported", category=UserWarning
            )
            environments.append(reference.copy())
        for candidate in environments:
            assert results(plain_text(candidate.step("next")[0])) == [24057]
        for action in ("random zero", "restart"):
            for candidate, expected in zip(environments, [14545, 14545, 14545, 18626], strict=True):
                # Measured Jericho 3.3.1 difference: copying with a pending seed
                # changes its next in-game reseed. Fernz preserves the active
                # host policy along with the current RNG and pending reset seed.
                assert results(plain_text(candidate.step(action)[0])) == [expected]
        for candidate in environments:
            assert results(plain_text(candidate.reset()[0])) == [18626]
    finally:
        for candidate in environments:
            candidate.close()


def test_zork_copy_replays_walkthrough_and_status_queries(zork1, walkthrough_trace):
    from jericho import FrotzEnv

    seed, actions, _, expected = walkthrough_trace
    env = FernzEnv(zork1, seed=seed)
    reference = FrotzEnv(str(zork1), seed=seed)
    environments = [env, reference]
    try:
        for candidate in environments:
            candidate.reset()
        for action, step in zip(actions[:35], expected[:35], strict=True):
            assert_zork_step(env.step(action), step, final=False)
            assert reference.step(action) == step
        original, native_original = env.get_state(), reference.get_state()
        fork, native_fork = env.copy(), reference.copy()
        environments += [fork, native_fork]
        for i, (action, step) in enumerate(zip(actions[35:], expected[35:], strict=True), start=35):
            actual = fork.step(action)
            assert_zork_step(actual, step, final=i == len(actions) - 1)
            assert native_fork.step(action) == step
            assert fork.get_score() == native_fork.get_score() == step[3]["score"]
            assert fork.get_moves() == actual[3]["moves"]
            assert native_fork.get_moves() == step[3]["moves"]
        assert fork.done and native_fork.victory()
        # Existing, explicit ending difference: the story's counter is 394;
        # Jericho reports 395 at final quit. Getters agree with each API's info.
        assert fork.get_moves() == 394 and native_fork.get_moves() == 395
        assert env.get_state() == original
        native_current = reference.get_state()
        for a, b in zip(native_current[:2], native_original[:2], strict=True):
            assert a.tobytes() == b.tobytes()
        assert native_current[2:] == native_original[2:]
        for candidate in (env, reference):
            assert candidate.get_score() == expected[34][3]["score"]
            assert candidate.get_moves() == expected[34][3]["moves"]
        assert_zork_step(env.step(actions[35]), expected[35], final=False)
        assert reference.step(actions[35]) == expected[35]
    finally:
        for candidate in environments:
            candidate.close()


@pytest.mark.smoke
def test_zork_status_queries_follow_save_restore_restart_and_checkpoints(
    zork1, tmp_path, monkeypatch
):
    from jericho import FrotzEnv

    monkeypatch.chdir(tmp_path)  # Jericho's SAVE writes its default zork1.qzl here.
    storage = Storage()
    env = FernzEnv(zork1, seed=12, save_handler=storage.save, restore_handler=storage.restore)
    reference = FrotzEnv(str(zork1), seed=12)
    try:
        for candidate in (env, reference):
            candidate.reset()
            assert (candidate.get_score(), candidate.get_moves()) == (0, 0)
        actions = [
            "open mailbox",
            "take leaflet",
            "north",
            "east",
            "open window",
            "enter",
            "save",
            "restart",
            "yes",
            "restore",
        ]
        for action in actions:
            actual, expected = env.step(action), reference.step(action)
            assert actual[3] == expected[3]
            assert env.get_score() == reference.get_score() == actual[3]["score"]
            assert env.get_moves() == reference.get_moves() == actual[3]["moves"]
            if action == "yes":
                assert actual[3] == {"score": 0, "moves": 0}
        assert (env.get_score(), env.get_moves()) == (10, 6)
        state, native_state = env.get_state(), reference.get_state()
        for candidate in (env, reference):
            candidate.reset()
            assert (candidate.get_score(), candidate.get_moves()) == (0, 0)
        env.set_state(state)
        reference.set_state(native_state)
        assert env.get_score() == reference.get_score() == 10
        assert env.get_moves() == reference.get_moves() == 6
    finally:
        env.close()
        reference.close()
