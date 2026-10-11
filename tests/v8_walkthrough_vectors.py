"""Full V8 trajectories and query contracts, with no reference dependency on replay."""

from dataclasses import replace

from .v5_trajectory_vectors import fernz_queries, reference_queries
from .v8_cases import ROUTES, SEED
from .v8_vectors import assert_record, capture, reset_fernz, text_content
from .vector_archive import digest


def capture_turn(env, original, game, action, response):
    observation, reward, done, info = response
    record = capture(env, original, game, action, observation)
    queries = reference_queries(env, original)
    case = ROUTES[game]
    assert queries["world_count"] == case["objects"]
    assert queries["player"] == case["player"] and queries["max_score"] == case["max_score"]
    record["reference_outcomes"] = {key: queries[key] for key in ("victory", "game_over")}
    if game == "anchor":
        # The story explicitly reports a win at 99/100, whereas the reference
        # labels that ending a loss. Keep the raw flags and recognize its text.
        hashes = {digest(" ".join(line.split()).encode()) for line in observation.splitlines()}
        queries["victory"] = (
            "0d16f9bc6f52536416b303975143cfc6f5b8b0d4689be47e784679b32117f65d" in hashes
        )
    # Follow Fernz's existing loss/victory contract: a winning restart menu
    # does not also classify the response as a loss. Retain the raw evidence.
    if queries["victory"]:
        queries["game_over"] = False
    record.update(
        queries=queries,
        reward=int(reward),
        reference_done=bool(done),
        info={key: int(info[key]) for key in ("score", "moves")},
    )
    return record


def check_turn(env, game, turn, record):
    if turn == 0:
        observation = reset_fernz(env, game)
        response = observation, 0, False, {"score": env.get_score(), "moves": env.get_moves()}
    else:
        response = env.step(record["action"], max_steps=2_000_000)
    before = env.get_state()
    assert_record(env, game, record, response[0], check_text=False)
    expected = record["queries"]
    count = expected["world_count"]
    direct = {1, count - 1, 1 + turn % (count - 1), expected["player"], expected["location"]}
    direct.update(expected["inventory"])
    actual = fernz_queries(env, direct_objects=None if turn == 0 else direct)
    assert actual == expected, {
        key: (actual[key], expected[key]) for key in actual if actual[key] != expected[key]
    }
    assert response[1] == record["reward"] and response[3] == record["info"]
    # These endings leave an input menu running; step.done means VM quit.
    assert response[2] is False
    assert record["reference_done"] == (expected["victory"] or expected["game_over"])
    assert env.get_state() == before, "Inspection changed the checkpoint"
    return response


def replay_walkthrough(path, game, documents):
    from fernz import FernzEnv

    case = ROUTES[game]
    header = documents["manifest.json"]
    assert digest(path.read_bytes()) == header["story"]["file_sha256"]
    route = documents["walkthrough.json"]["cases"][0]
    assert route["seed"] == SEED and len(route["steps"]) == case["length"] + 1
    checkpoints = {1, case["length"] // 3, 2 * case["length"] // 3, case["length"]}
    env = FernzEnv(path, seed=SEED, **header["geometry"])
    text = []
    try:
        for turn, record in enumerate(route["steps"]):
            before = env.get_state() if turn in checkpoints else None
            try:
                response = check_turn(env, game, turn, record)
                text.append(
                    text_content(
                        response[0],
                        game,
                        opening=turn == 0,
                        after_character=record["after_character"],
                        fernz=True,
                    )
                )
                if record["text_group_end"]:
                    normalized = " ".join(" ".join(text).split())
                    assert digest(normalized.encode()) == record["text_sha256"], normalized
                    text.clear()
                else:
                    assert record["text_sha256"] is None
                if before is not None:
                    after = env.get_state()
                    fork = env.copy()
                    try:
                        assert fork.get_state() == after
                        fork.set_state(before)
                        assert check_turn(fork, game, turn, record) == response
                        assert fork.get_state() == after and env.get_state() == after
                    finally:
                        fork.close()
            except (AssertionError, RuntimeError, ValueError) as error:
                error.add_note(f"{game}: turn {turn}, action {record['action']!r}")
                raise
        assert not text and env.victory() and not env.game_over() and not env.done
        assert env.get_score() == case["score"]
        final = env.get_state()
        reset_fernz(env, game)
        assert not env.victory()
        env.set_state(final)
        assert env.victory() and env.get_state() == final
    finally:
        env.close()


def replay_counters(path, game, document):
    from fernz import FernzEnv

    env = FernzEnv(path, seed=SEED)
    try:
        reset_fernz(env, game)
        saved = env.get_state()
        base = int.from_bytes(saved.ram[12:14], "big")
        for record in document["cases"][0]["steps"]:
            ram = bytearray(saved.ram)
            address = base + 2 * ROUTES[game][f"{record['field']}_global"]
            ram[address : address + 2] = record["value"].to_bytes(2, "big")
            changed = replace(saved, ram=bytes(ram))
            env.set_state(changed)
            assert (env.get_score(), env.get_moves()) == (record["score"], record["moves"]), record
            assert env.get_state() == changed
    finally:
        env.close()
