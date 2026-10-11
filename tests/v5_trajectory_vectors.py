"""Shared live-reference measurements and portable full-trajectory assertions."""

import re
from dataclasses import asdict

from .observation_helpers import window_text
from .v5_corpus_vectors import object_fingerprint, object_layout, observation_text, reset_fernz
from .v5_oracle import assert_public_object, object_records
from .v5_trajectory_cases import GAMES
from .vector_archive import digest


def boxed_text(observation, game):
    if game != "sherlock":
        return None
    match = re.fullmatch(
        r'>\n {9,39}("[^\n]+") +(?:Saturday|Sunday|Monday) +\d+:\d{2}:\d{2} [ap]\.m\.\n',
        observation,
    )
    return " ".join(match[1].split()) if match else None


def text_content(observation, game, *, opening=False, fernz=False):
    if fernz:
        observation = window_text(observation)
    if game == "balances" and not fernz:
        observation = re.sub(r" {127,128}[^\n]{1,40}Score: -?\d+Moves: \d+$", "", observation)
    if game == "sherlock":
        if fernz:
            observation = observation.replace(
                "Interpreter 6 Version F Serial Number 871214",
                "Interpreter 1 Version F Serial Number 871214",
            )
        else:
            observation = observation.replace(" " * 128 + "Score:", "")
    text = observation_text(observation, game, opening=opening, fernz=fernz)
    if fernz and game == "balances" and text.endswith("or QUIT?"):
        text = text[:-1]
    return text


def reference_queries(env, original):
    state = env.get_state()
    ram = state[0].tobytes()
    records = object_records(ram + original[len(ram) :], original)
    world = env.get_world_objects(clean=False)
    assert len(world) == len(records)
    for obj, record in zip(world, records, strict=True):
        assert_public_object(obj, record)
    player = int(env.get_player_object().num)
    parent = records[player]["parent"]
    carried = []
    number = records[player]["child"]
    while number:
        assert number not in carried
        carried.append(number)
        number = records[number]["sibling"]
    assert_public_object(env.get_player_object(), records[player])
    assert_public_object(env.get_player_location(), records[parent])
    inventory = env.get_inventory()
    assert [int(obj.num) for obj in inventory] == carried[: len(inventory)]
    if len(inventory) < len(carried):
        # As in V3, the public wrapper stops at an unnamed child. RAM still
        # provides the complete, independently decoded inventory chain.
        hidden = carried[len(inventory)]
        assert records[hidden]["name"] == "" and env.get_object(hidden) is None
    for obj in inventory:
        assert_public_object(obj, records[int(obj.num)])
    return query_record(records, player, parent, carried, env)


def query_record(records, player, parent, carried, env):
    return {
        "world_count": len(records),
        "world_sha256": digest(records),
        "player": player,
        "player_sha256": digest(records[player]),
        "location": parent,
        "location_sha256": digest(records[parent]) if parent else digest(None),
        "inventory": carried,
        "inventory_sha256": digest([records[n] for n in carried]),
        "score": int(env.get_score()),
        "moves": int(env.get_moves()),
        "max_score": int(env.get_max_score()),
        "game_over": bool(env.game_over()),
        "victory": bool(env.victory()),
    }


def fernz_queries(env):
    world = env.get_world_objects()
    records = [asdict(obj) for obj in world]
    assert env.get_object(0) is None and env.get_object(len(world)) is None
    for obj in world[1:]:
        assert env.get_object(obj.num) == obj
    player = env.get_player_object()
    location = env.get_player_location()
    return query_record(
        records,
        player.num,
        location.num if location else 0,
        [obj.num for obj in env.get_inventory()],
        env,
    )


def capture(env, original, game, action, response):
    observation, reward, done, info = response
    queries = reference_queries(env, original)
    assert queries["player"] == GAMES[game]["player"]
    assert queries["max_score"] == GAMES[game]["max_score"]
    state = env.get_state()
    terminal = game == "sherlock" and queries["game_over"]
    if not terminal:
        assert int(state[6]) in (0xE4, 0xF6)
    a, period, counter = state[7]
    box = boxed_text(observation, game)
    return {
        "action": action,
        "queries": queries,
        "reward": int(reward),
        "reference_done": bool(done),
        "info": {key: int(info[key]) for key in ("score", "moves")},
        "terminal_menu": terminal,
        "input_address": None if terminal else int(state[2]) - 1,
        "character_input": terminal or int(state[6]) == 0xF6,
        "rng": [int(a) & 0x7FFFFFFF, int(period), int(counter) if period else 0],
        "objects": object_fingerprint(state[0].tobytes(), object_layout(original)),
        "upper_window_sha256": digest(box.encode()) if box is not None else None,
        "observation_sha256": None
        if action is None and game == "sherlock"
        else digest(
            (
                "" if box is not None else text_content(observation, game, opening=action is None)
            ).encode()
        ),
    }


def check_step(env, game, record):
    if record["action"] is None:
        observation = reset_fernz(env, game)
        response = (observation, 0, False, {"score": env.get_score(), "moves": env.get_moves()})
    else:
        response = env.step(record["action"])
        observation = response[0]
    state = env.get_state()
    assert not env.done
    assert state.input_request.character == record["character_input"]
    if record["input_address"] is not None:
        assert state.input_request.instruction_address == record["input_address"]
    assert [state.rng.state, state.rng.period, state.rng.position] == record["rng"]
    assert object_fingerprint(state.ram, object_layout(env.story.data)) == record["objects"]
    assert fernz_queries(env) == record["queries"], (
        game,
        record["action"],
        fernz_queries(env),
        record["queries"],
    )
    assert env.get_state() == state, "Inspection mutated the checkpoint"
    assert response[1] == record["reward"] and response[-1] == record["info"]
    assert record["reference_done"] == (env.game_over() or env.victory())
    if record["upper_window_sha256"] is not None:
        assert (
            digest(" ".join(window_text(observation, 1, minimum_split=3).split()).encode())
            == record["upper_window_sha256"]
        )
    if record["observation_sha256"] is not None:
        text = text_content(observation, game, opening=record["action"] is None, fernz=True)
        assert digest(text.encode()) == record["observation_sha256"], (game, record["action"], text)
    return response


def replay_trajectory(path, game, documents):
    from fernz import FernzEnv

    from .test_save_restore import Storage
    from .v5_corpus import story_identity
    from .v5_trajectory_cases import SEED

    assert digest(path.read_bytes()) == story_identity(game)["file_sha256"]
    assert documents["manifest.json"]["kind"] == "v5-trajectory"
    storage = Storage()
    env = FernzEnv(path, seed=SEED, save_handler=storage.save, restore_handler=storage.restore)
    try:
        checkpoints = {}
        for turn, record in enumerate(documents["walkthrough.json"]["cases"][0]["steps"]):
            before = env.get_state() if turn else None
            check_step(env, game, record)
            after = env.get_state()
            if before is not None:
                env.set_state(before)
                check_step(env, game, record)
                assert env.get_state() == after
            if turn in GAMES[game]["checkpoints"]:
                checkpoints[turn] = after
        assert env.victory() and env.get_score() == GAMES[game]["winning_score"]
        for name, document in documents.items():
            if name in ("manifest.json", "breadth.json", "walkthrough.json"):
                continue
            for case in document["cases"]:
                if name == "seeds.json":
                    env.seed(case["seed"])
                    first, *records = case["steps"]
                    check_step(env, game, first)
                    before = env.get_state()
                    fork = env.copy()
                    try:
                        for record in records:
                            check_step(fork, game, record)
                        assert env.get_state() == before
                        check_step(fork, game, first)
                        assert fork.get_state() == before
                    finally:
                        fork.close()
                else:
                    env.set_state(checkpoints[case["checkpoint"]])
                    for record in case["steps"]:
                        before = env.get_state()
                        check_step(env, game, record)
                        after = env.get_state()
                        env.set_state(before)
                        check_step(env, game, record)
                        assert env.get_state() == after
        assert storage.saves > 0 and storage.restores > 0
    finally:
        env.close()
