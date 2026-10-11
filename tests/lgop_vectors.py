"""Portable LGOP replay shared by live-reference and committed-vector checks."""

from dataclasses import asdict

import pytest

from fernz import FernzEnv

from .lgop_cases import CHECKPOINTS, PLAYER, SEED, STORY
from .test_save_restore import Storage
from .vector_archive import digest, state_fingerprint


def check_step(env, record):
    action = record["action"]
    result = env.reset() if action is None else env.step(action)
    before = env.get_state()
    assert state_fingerprint(before) == record["state"], action
    assert not env.done
    expected = record["queries"]
    world = env.get_world_objects()
    player = env.get_player_object()
    location = env.get_player_location()
    inventory = env.get_inventory()
    assert player.num == PLAYER and player == world[PLAYER]
    assert location == (world[player.parent] if player.parent else None)
    actual = {
        "score": env.get_score(),
        "moves": env.get_moves(),
        "player": player.num,
        "location": player.parent,
        "inventory": [obj.num for obj in inventory],
        "world_count": len(world),
        "world_sha256": digest([asdict(obj) for obj in world]),
        "player_sha256": digest(asdict(player)),
        "location_sha256": digest(asdict(location) if location else None),
        "inventory_sha256": digest([asdict(obj) for obj in inventory]),
        "game_over": env.game_over(),
        "victory": env.victory(),
    }
    assert actual == expected, action
    assert result[-1] == {key: expected[key] for key in ("score", "moves")}
    if action is not None:
        assert result[1] == record["reward"] and result[2] is False
    assert env.get_state() == before, "Read-only queries changed the state"
    return result[0].text.removesuffix(">").removesuffix(" ")


def check_case(env, case, checkpoints=None, *, record_checkpoints=False):
    texts = []
    for turn, record in enumerate(case["steps"]):
        try:
            before = env.get_state() if record["action"] is not None else None
            text = check_step(env, record)
            after = env.get_state()
            if before is not None:
                env.set_state(before)
                assert check_step(env, record) == text
                assert env.get_state() == after
            texts.append(text)
            if record_checkpoints and turn in CHECKPOINTS:
                checkpoints[turn] = after
        except (AssertionError, RuntimeError, ValueError) as error:
            error.add_note(f"LGOP {case['id']}, input {turn}, {record['action']!r}")
            raise
    assert digest("".join(texts).encode()) == case["text_sha256"], case["id"]


def replay(path, documents, *, smoke=False):
    assert documents["manifest.json"]["story"] == STORY
    assert digest(path.read_bytes()) == STORY["file_sha256"]
    storage = Storage()
    env = FernzEnv(path, seed=SEED, save_handler=storage.save, restore_handler=storage.restore)
    try:
        with pytest.raises(NotImplementedError, match="no fixed maximum"):
            env.get_max_score()
        checkpoints = {}
        route = documents["smoke.json" if smoke else "walkthrough.json"]["cases"][0]
        check_case(env, route, checkpoints, record_checkpoints=True)
        if smoke:
            assert len(route["steps"]) == 5
            return
        assert len(route["steps"]) == 390
        assert env.victory() and not env.game_over() and not env.done
        assert (env.get_score(), env.get_moves()) == (326, 393)
        final = env.get_state()
        env.reset()
        assert not env.victory()
        env.set_state(final)
        assert env.victory()
        for name in ("detours.json", "lifecycle.json", "partials.json"):
            for case in documents[name]["cases"]:
                env.seed(case["seed"])
                if case["checkpoint"] is not None:
                    env.set_state(checkpoints[case["checkpoint"]])
                check_case(env, case)
        assert storage.saves == 6 and storage.restores == 6
        for turn, state in checkpoints.items():
            env.set_state(state)
            fork = env.copy()
            try:
                world = fork.get_world_objects()
                for number, obj in enumerate(world):
                    assert fork.get_object(number) == (obj if number else None)
                player = fork.get_player_object()
                inventory = fork.get_inventory()
                player.parent = 0
                world[1].name = "edited"
                world[1].attr[:] = [1] * 32
                if inventory:
                    inventory[0].properties[:] = [31] * 16
                assert fork.get_state() == state
                check_step(fork, route["steps"][turn + 1])
                assert env.get_state() == state
            finally:
                fork.close()
    finally:
        env.close()
