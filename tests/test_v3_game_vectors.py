"""Replay all retained V3 games without Jericho, NumPy, or ZIP extraction."""

from pathlib import Path

import pytest

from fernz import FernzEnv

from .test_save_restore import Storage
from .v3_cases import (
    BOOT_ACTIONS,
    COMMANDS,
    DEATHS,
    EXTRA_ROUTES,
    GAME_COMMANDS,
    GAMES,
    MECHANICS,
    SEEDS,
    checkpoint_turns,
)
from .v3_vectors import query_fingerprint, step_and_check
from .vector_archive import REFERENCE_VERSION, digest, read_archive

pytestmark = [pytest.mark.rom, pytest.mark.vectors, pytest.mark.v3games]


@pytest.fixture(scope="module")
def v3_archive(v3_game, jericho_games):
    game = v3_game
    path = jericho_games / GAMES[game]["filename"]
    documents = read_archive(Path(__file__).parent / "vectors" / f"{game}_vectors.zip")
    manifest = documents["manifest.json"]
    assert manifest["kind"] == "v3-gameplay" and manifest["game"] == game
    assert manifest["story"] == GAMES[game]
    assert manifest["state_format_version"] == 2
    assert manifest["reference"]["version"] == REFERENCE_VERSION
    assert manifest["seed"] == GAMES[game]["seed"]
    assert manifest["boot_actions"] == list(BOOT_ACTIONS.get(game, ()))
    assert digest(path.read_bytes()) == GAMES[game]["file_sha256"]
    route = documents["walkthrough.json"]["cases"][0]
    assert len(route["steps"]) == GAMES[game]["walkthrough_length"] + 1
    assert route["steps"][-1]["queries"]["victory"]
    for turn in checkpoint_turns(game):
        cases = documents[f"detours/{turn}.json"]["cases"]
        assert len(cases) == len(COMMANDS) + len(GAME_COMMANDS[game])
        assert {case["id"] for case in cases} == {
            *(f"common:{i}" for i in range(len(COMMANDS))),
            *(f"game:{i}" for i in range(len(GAME_COMMANDS[game]))),
        }
    assert [case["seed"] for case in documents["seeds.json"]["cases"]] == [
        *SEEDS,
        *EXTRA_ROUTES.get(game, ()),
    ]
    scenarios = documents["scenarios.json"]["cases"]
    assert {case["id"] for case in scenarios} == {
        "loss-and-continuation",
        "save-restore-restart",
        *(name for name, _, _ in MECHANICS.get(game, ())),
    }
    return game, path, documents


@pytest.fixture(scope="module")
def v3_states(v3_archive):
    game, path, documents = v3_archive
    env = FernzEnv(path, seed=GAMES[game]["seed"])
    states = []
    try:
        for turn, record in enumerate(documents["walkthrough.json"]["cases"][0]["steps"]):
            try:
                step_and_check(env, record, game)
            except (AssertionError, RuntimeError, ValueError) as error:
                error.add_note(f"{game}: complete vector walkthrough turn {turn}")
                raise
            states.append(env.get_state())
        assert env.victory() and env.get_score() == env.get_max_score()
        return states
    finally:
        env.close()


@pytest.fixture
def v3_storage():
    return Storage()


@pytest.fixture
def v3_env(v3_archive, v3_storage):
    game, path, _ = v3_archive
    storage = v3_storage
    env = FernzEnv(
        path, seed=GAMES[game]["seed"], save_handler=storage.save, restore_handler=storage.restore
    )
    try:
        yield env
    finally:
        env.close()


def test_complete_walkthrough_restored_continuations_and_reset(v3_archive, v3_states, v3_env):
    game, _, documents = v3_archive
    route = documents["walkthrough.json"]["cases"][0]["steps"]
    for turn, record in enumerate(route[1:], 1):
        v3_env.set_state(v3_states[turn - 1])
        step_and_check(v3_env, record, game)
        assert v3_env.get_state() == v3_states[turn]
    step_and_check(v3_env, route[0], game)
    assert v3_env.get_state() == v3_states[0]


def replay_branch(env, case, states, game):
    final = None
    for _ in range(2):
        env.set_state(states[case["checkpoint"]])
        for record in case["steps"]:
            step_and_check(env, record, game)
        if final is not None:
            assert env.get_state() == final
        final = env.get_state()


@pytest.mark.parametrize("checkpoint", range(5))
@pytest.mark.parametrize("index", range(len(COMMANDS)), ids=COMMANDS)
def test_common_detours(v3_archive, v3_states, v3_env, checkpoint, index):
    game, _, documents = v3_archive
    turn = checkpoint_turns(game)[checkpoint]
    case = next(
        case
        for case in documents[f"detours/{turn}.json"]["cases"]
        if case["id"] == f"common:{index}"
    )
    assert case["steps"][0]["action"] == COMMANDS[index]
    replay_branch(v3_env, case, v3_states, game)


@pytest.mark.parametrize("checkpoint", range(5))
@pytest.mark.parametrize("index", range(10))
def test_game_specific_detours(v3_archive, v3_states, v3_env, checkpoint, index):
    game, _, documents = v3_archive
    turn = checkpoint_turns(game)[checkpoint]
    case = next(
        case for case in documents[f"detours/{turn}.json"]["cases"] if case["id"] == f"game:{index}"
    )
    assert case["steps"][0]["action"] == GAME_COMMANDS[game][index]
    replay_branch(v3_env, case, v3_states, game)


def test_loss_mechanics_save_restore_and_restart(v3_archive, v3_states, v3_env, v3_storage):
    game, _, documents = v3_archive
    for case in documents["scenarios.json"]["cases"]:
        replay_branch(v3_env, case, v3_states, game)
        if case["id"] == "loss-and-continuation":
            loss = case["steps"][len(DEATHS[game][1]) - 1]
            assert loss["queries"]["game_over"] and not loss["queries"]["victory"]
            assert not loss["halted"]
    assert v3_storage.saves == v3_storage.restores == 2


@pytest.mark.parametrize("seed", SEEDS)
def test_other_seeds_and_deferred_reset(v3_archive, v3_env, seed):
    game, _, documents = v3_archive
    case = next(case for case in documents["seeds.json"]["cases"] if case["seed"] == seed)
    v3_env.reset()
    before = v3_env.get_state()
    assert v3_env.seed(seed) == seed
    assert v3_env.get_state() == before
    final = None
    for _ in range(2):
        for record in case["steps"]:
            step_and_check(v3_env, record, game)
        if final is not None:
            assert v3_env.get_state() == final
        final = v3_env.get_state()


@pytest.mark.parametrize("checkpoint", range(5))
def test_independent_copies_and_detached_object_queries(v3_archive, v3_states, v3_env, checkpoint):
    game, _, documents = v3_archive
    turn = checkpoint_turns(game)[checkpoint]
    v3_env.set_state(v3_states[turn])
    fork = v3_env.copy()
    try:
        world = fork.get_world_objects()
        for number, obj in enumerate(world):
            assert fork.get_object(number) == (obj if number else None)
        player = fork.get_player_object()
        assert player.num == GAMES[game]["player"]
        assert player == world[player.num]
        inventory = fork.get_inventory()
        child = player.child
        for obj in inventory:
            assert obj.num == child and obj.parent == player.num
            child = obj.sibling
        assert child == 0
        before = query_fingerprint(fork)
        world[1].name = "edited"
        world[1].attr[:] = [1] * 32
        player.parent = 0
        if inventory:
            inventory[0].properties[:] = [31] * 16
        assert query_fingerprint(fork) == before
        record = documents["walkthrough.json"]["cases"][0]["steps"][turn + 1]
        step_and_check(fork, record, game)
        assert fork.get_state() == v3_states[turn + 1]
        assert v3_env.get_state() == v3_states[turn]
    finally:
        fork.close()


def test_additional_complete_seeded_routes(v3_archive, v3_env):
    game, _, documents = v3_archive
    for seed in EXTRA_ROUTES.get(game, ()):
        case = next(case for case in documents["seeds.json"]["cases"] if case["seed"] == seed)
        assert case["complete_route"]
        assert len(case["steps"]) == GAMES[game]["walkthrough_length"] + 1
        v3_env.seed(seed)
        final = None
        for _ in range(2):
            for record in case["steps"]:
                step_and_check(v3_env, record, game)
            assert v3_env.victory() and v3_env.get_score() == GAMES[game]["max_score"]
            if final is not None:
                assert v3_env.get_state() == final
            final = v3_env.get_state()
