"""Replay recorded public reference behavior on every supported host platform."""

import pytest

from fernz import FernzEnv

from .test_save_restore import Storage
from .vector_archive import (
    REFERENCE_VERSION,
    digest,
    observation_text,
    query_fingerprint,
    read_archive,
    state_fingerprint,
)
from .zork_scenarios import CHECKPOINTS, WALKTHROUGH_SEED, ZORK1_SHA256

pytestmark = [pytest.mark.rom, pytest.mark.vectors]
DOCUMENTS = read_archive()
MANIFEST = DOCUMENTS["manifest.json"]
WALKTHROUGH = DOCUMENTS["walkthrough.json"]["cases"][0]
BRANCHES = [
    pytest.param(case, id=f"{name.removesuffix('.json')}:{case['id']}")
    for name, document in DOCUMENTS.items()
    if name not in {"manifest.json", "walkthrough.json", "combat.json"}
    for case in document["cases"]
]
COMBAT = [pytest.param(case, id=case["id"]) for case in DOCUMENTS["combat.json"]["cases"]]


def assert_record(env, response, record):
    opening = record["action"] is None
    observation, reward, done, info = (response[0], 0, False, response[1]) if opening else response
    mode = record["observation_mode"]
    assert digest(observation_text(observation, mode).encode()) == record["observation_sha256"], (
        f"Observation differs for {record['action']!r}: {observation!r}"
    )
    assert type(reward) is int and reward == record["reward"]
    assert type(done) is bool and done is (mode == "ending")
    assert env.done is done
    assert set(info) == {"score", "moves"}
    assert all(type(value) is int for value in info.values())
    expected_info = record["info"]
    if mode == "ending":
        # Pinned winning ending: Fernz stops at quit with the story's counter;
        # the reference reports one additional move. Keep this narrow and exact.
        assert expected_info == {"score": 350, "moves": 395}
        expected_info = {"score": 350, "moves": 394}
    assert info == expected_info
    before = env.get_state()
    queries = query_fingerprint(env, fernz=True)
    expected_queries = record["queries"]
    if mode == "ending":
        expected_queries = {**expected_queries, "moves": 394}
    assert queries == expected_queries
    assert record["done"] is (queries["game_over"] or queries["victory"])
    assert env.get_state() == before, "Inspection changed VM state"
    if mode == "ending":
        assert record["state"] is None  # Native bridge supports pending reads only.
    else:
        assert state_fingerprint(before) == record["state"]


def step_and_check(env, record):
    try:
        response = env.reset() if record["action"] is None else env.step(record["action"])
        assert_record(env, response, record)
        return response
    except (AssertionError, RuntimeError, ValueError) as error:
        error.add_note(
            f"Vector action: {record['action']!r}; expected room {record['queries']['location']}"
        )
        raise


@pytest.fixture(scope="module")
def vector_story(jericho_games):
    assert MANIFEST["story"] == {"filename": "zork1.z5", "version": 3, "sha256": ZORK1_SHA256}
    assert MANIFEST["reference"]["version"] == REFERENCE_VERSION
    assert MANIFEST["state_format_version"] == 2
    assert MANIFEST["seed"] == WALKTHROUGH_SEED
    assert MANIFEST["checkpoints"] == {
        name: {"turn": turn, "location": location} for name, (turn, location) in CHECKPOINTS.items()
    }
    path = jericho_games / MANIFEST["story"]["filename"]
    assert digest(path.read_bytes()) == ZORK1_SHA256, "Unexpected vector ROM"
    return path


@pytest.fixture(scope="module")
def walkthrough_states(vector_story):
    env = FernzEnv(vector_story, seed=WALKTHROUGH["seed"])
    try:
        states = []
        for turn, record in enumerate(WALKTHROUGH["steps"]):
            try:
                step_and_check(env, record)
                states.append(env.get_state())
            except (AssertionError, RuntimeError, ValueError) as error:
                error.add_note(f"Recorded walkthrough turn {turn}")
                raise
        assert len(states) == 397 and env.done and env.victory()
        return states
    finally:
        env.close()


def test_complete_walkthrough_reset_and_snapshot_replay(vector_story, walkthrough_states):
    env = FernzEnv(vector_story, seed=WALKTHROUGH["seed"])
    try:
        # Replay every continuation from a restored snapshot, including victory.
        for turn, record in enumerate(WALKTHROUGH["steps"][1:], 1):
            env.set_state(walkthrough_states[turn - 1])
            step_and_check(env, record)
            assert env.get_state() == walkthrough_states[turn]
        assert env.done
        step_and_check(env, WALKTHROUGH["steps"][0])
        assert env.get_state() == walkthrough_states[0]
    finally:
        env.close()


@pytest.mark.parametrize("case", BRANCHES)
def test_branch_and_checkpoint_replay(vector_story, walkthrough_states, case):
    checkpoint = MANIFEST["checkpoints"][case["checkpoint"]]["turn"]
    storage = Storage()
    env = FernzEnv(
        vector_story,
        seed=WALKTHROUGH_SEED,
        save_handler=storage.save,
        restore_handler=storage.restore,
    )
    try:
        for _ in range(2):
            env.set_state(walkthrough_states[checkpoint])
            for record in case["steps"]:
                step_and_check(env, record)
    finally:
        env.close()


@pytest.mark.parametrize("case", COMBAT)
def test_seeded_combat_and_deferred_host_seed(vector_story, case):
    env = FernzEnv(vector_story, seed=999)
    try:
        env.reset()
        before = env.get_state()
        assert env.seed(case["seed"]) == case["seed"]
        assert env.get_state() == before  # Seed applies at the next reset.
        for _ in range(2):
            for record in case["steps"]:
                step_and_check(env, record)
    finally:
        env.close()


@pytest.mark.parametrize("turn", (0, 35, 218, 387, 396))
def test_copies_and_detached_object_queries(vector_story, walkthrough_states, turn):
    env = FernzEnv(vector_story, seed=WALKTHROUGH_SEED)
    fork = None
    try:
        state = walkthrough_states[turn]
        env.set_state(state)
        fork = env.copy()
        assert fork.get_state() == state
        world = fork.get_world_objects()
        for number, obj in enumerate(world):
            assert fork.get_object(number) == (obj if number else None)
        player = fork.get_player_object()
        assert player == world[player.num]
        assert fork.get_player_location() == world[player.parent]
        held_inventory = fork.get_inventory()
        inventory_numbers = [obj.num for obj in held_inventory]
        child = player.child
        for number in inventory_numbers:
            assert number == child
            assert world[number].parent == player.num
            child = world[number].sibling
        assert child == 0
        # Mutating a returned snapshot must affect neither environment.
        player.parent = 0
        world[160].attr[:] = [1] * 32
        world[160].properties[:] = [31] * 16
        assert query_fingerprint(fork, fernz=True) == query_fingerprint(env, fernz=True)
        if turn < 396:
            step_and_check(fork, WALKTHROUGH["steps"][turn + 1])
        else:
            step_and_check(fork, WALKTHROUGH["steps"][0])
        assert env.get_state() == state
        assert fork.get_state() != state
    finally:
        if fork is not None:
            fork.close()
        env.close()
