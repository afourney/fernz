"""Complete V3 routes and detours compared live through public Jericho APIs."""

import pytest

from fernz import FernzEnv

from .test_save_restore import Storage
from .v3_cases import (
    COMMANDS,
    DEATHS,
    EXTRA_ROUTES,
    GAME_COMMANDS,
    GAMES,
    LOSS_CONTINUATIONS,
    MECHANICS,
    SEED_FOLLOWUPS,
    SEED_PREFIX_LENGTH,
    SEEDS,
    checkpoint_turns,
    lifecycle_actions,
)
from .v3_reference import Reference
from .v3_vectors import query_fingerprint, step_and_check

pytestmark = [pytest.mark.reference, pytest.mark.v3games]


@pytest.fixture(scope="module")
def v3_walkthrough(v3_game, jericho_games):
    game = v3_game
    path = jericho_games / GAMES[game]["filename"]
    reference = Reference(path, game)
    storage = Storage()
    reference.storage = storage
    env = FernzEnv(
        path, seed=reference.seed, save_handler=storage.save, restore_handler=storage.restore
    )
    actions = reference.env.get_walkthrough()
    assert len(actions) == GAMES[game]["walkthrough_length"]
    states, native_states, records = [], [], []
    try:
        for turn, action in enumerate((None, *actions)):
            record = reference.opening() if action is None else reference.step(action)
            try:
                step_and_check(env, record, game)
            except (AssertionError, RuntimeError, ValueError) as error:
                error.add_note(f"{game}: complete walkthrough turn {turn}")
                raise
            states.append(env.get_state())
            native_states.append(reference.env.get_state())
            records.append(record)
        assert env.victory() and reference.env.victory()
        assert env.get_score() == env.get_max_score()
        yield game, env, reference, states, native_states, records
    finally:
        env.close()
        reference.close()


def test_complete_route_reset_and_every_restored_continuation(v3_walkthrough):
    game, env, reference, states, native_states, records = v3_walkthrough
    for turn, record in enumerate(records[1:], 1):
        env.set_state(states[turn - 1])
        reference.env.set_state(native_states[turn - 1])
        assert reference.step(record["action"]) == record
        step_and_check(env, record, game)
        assert env.get_state() == states[turn]
    step_and_check(env, records[0], game)
    assert env.get_state() == states[0]


@pytest.mark.parametrize("checkpoint", range(5))
@pytest.mark.parametrize("action", COMMANDS, ids=lambda action: action or "<empty>")
def test_detour_and_followups(v3_walkthrough, checkpoint, action):
    game, env, reference, states, native_states, _ = v3_walkthrough
    turn = checkpoint_turns(game)[checkpoint]
    env.set_state(states[turn])
    reference.env.set_state(native_states[turn])
    records = []
    for command in (action, "look", "inventory"):
        record = reference.step(command)
        step_and_check(env, record, game)
        records.append(record)
        if record["done"]:
            break
    # Replay the branch, including its RNG and parser history, from a snapshot.
    expected = env.get_state()
    env.set_state(states[turn])
    for record in records:
        step_and_check(env, record, game)
    assert env.get_state() == expected


@pytest.mark.parametrize("checkpoint", range(5))
@pytest.mark.parametrize("index", range(10))
def test_game_specific_detours(v3_walkthrough, checkpoint, index):
    game = v3_walkthrough[0]
    test_detour_and_followups(v3_walkthrough, checkpoint, GAME_COMMANDS[game][index])


def test_loss_sequence_and_continued_input(v3_walkthrough):
    game, env, reference, states, native_states, _ = v3_walkthrough
    turn, actions = DEATHS[game]
    env.set_state(states[turn])
    reference.env.set_state(native_states[turn])
    for action in actions:
        step_and_check(env, reference.step(action), game)
    assert env.game_over() and not env.victory()
    assert not env.done
    for action in LOSS_CONTINUATIONS.get(game, ("look", "inventory")):
        step_and_check(env, reference.step(action), game)


def test_game_specific_mechanics(v3_walkthrough):
    game, env, reference, states, native_states, _ = v3_walkthrough
    for name, turn, actions in MECHANICS.get(game, ()):
        env.set_state(states[turn])
        reference.env.set_state(native_states[turn])
        records = []
        for action in actions:
            record = reference.step(action)
            step_and_check(env, record, game)
            records.append(record)
        final = env.get_state()
        env.set_state(states[turn])
        for record in records:
            step_and_check(env, record, game)
        assert env.get_state() == final, name


def test_save_restore_and_restart(v3_walkthrough, tmp_path, monkeypatch):
    game, env, reference, states, native_states, _ = v3_walkthrough
    monkeypatch.chdir(tmp_path)
    turn = checkpoint_turns(game)[1]
    env.set_state(states[turn])
    reference.env.set_state(native_states[turn])
    before = reference.storage.saves, reference.storage.restores
    for action in lifecycle_actions(game):
        step_and_check(env, reference.step(action), game)
    assert (reference.storage.saves, reference.storage.restores) == (before[0] + 1, before[1] + 1)


@pytest.mark.parametrize("checkpoint", range(5))
def test_copies_and_detached_objects(v3_walkthrough, checkpoint):
    game, env, _reference, states, _native_states, records = v3_walkthrough
    turn = checkpoint_turns(game)[checkpoint]
    env.set_state(states[turn])
    fork = env.copy()
    try:
        world = fork.get_world_objects()
        for number, obj in enumerate(world):
            assert fork.get_object(number) == (obj if number else None)
        player = fork.get_player_object()
        inventory = fork.get_inventory()
        assert player == world[GAMES[game]["player"]]
        assert fork.get_player_location() == (world[player.parent] if player.parent else None)
        child = player.child
        for obj in inventory:
            assert obj.num == child and obj.parent == player.num
            child = obj.sibling
        assert child == 0
        before = query_fingerprint(fork)
        player.parent = 0
        world[1].attr[:] = [1] * 32
        world[1].name = "edited"
        if inventory:
            inventory[0].properties[:] = [31] * 16
        assert query_fingerprint(fork) == before
        step_and_check(fork, records[turn + 1], game)
        assert env.get_state() == states[turn]
        assert fork.get_state() == states[turn + 1]
    finally:
        fork.close()


@pytest.mark.parametrize("direction", ("into_fernz", "into_jericho"))
def test_state_interchange_continues_to_the_ending(v3_walkthrough, direction):
    game, env, reference, states, native_states, records = v3_walkthrough
    turn = checkpoint_turns(game)[2]
    if direction == "into_fernz":
        env.set_state(reference.bridge.from_jericho(native_states[turn]))
        reference.env.set_state(native_states[turn])
    else:
        env.set_state(states[turn])
        reference.env.set_state(reference.bridge.to_jericho(states[turn]))
    for record in records[turn + 1 :]:
        assert reference.step(record["action"]) == record
        step_and_check(env, record, game)


@pytest.mark.parametrize("seed", SEEDS)
def test_other_seeds_reset_and_replay(v3_walkthrough, seed):
    game, original, _, _, _, route = v3_walkthrough
    reference = Reference(original.game_path, game, seed)
    env = FernzEnv(original.game_path, seed=seed)
    try:
        records = [reference.opening()]
        step_and_check(env, records[0], game)
        for action in (
            *[r["action"] for r in route[1 : 1 + SEED_PREFIX_LENGTH.get(game, 10)]],
            *SEED_FOLLOWUPS.get(game, (*("wait",) * 5, "look", "inventory")),
        ):
            record = reference.step(action)
            step_and_check(env, record, game)
            records.append(record)
            if record["done"]:
                break
        final = env.get_state()
        for record in records:
            step_and_check(env, record, game)
        assert env.get_state() == final
    finally:
        env.close()
        reference.close()


def test_additional_complete_seeded_routes(v3_walkthrough):
    game, original, _, _, _, route = v3_walkthrough
    for seed in EXTRA_ROUTES.get(game, ()):
        reference = Reference(original.game_path, game, seed)
        env = FernzEnv(original.game_path, seed=seed)
        try:
            records = [reference.opening()]
            step_and_check(env, records[0], game)
            for original_record in route[1:]:
                record = reference.step(original_record["action"])
                step_and_check(env, record, game)
                records.append(record)
            assert env.victory() and env.get_score() == GAMES[game]["max_score"]
            final = env.get_state()
            for record in records:
                step_and_check(env, record, game)
            assert env.get_state() == final
        finally:
            env.close()
            reference.close()
