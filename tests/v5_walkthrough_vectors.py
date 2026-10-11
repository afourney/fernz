"""Complete retained V5 routes: public reference recording and portable replay."""

from dataclasses import replace

from .v5_corpus_vectors import object_fingerprint, object_layout, reset_fernz
from .v5_trajectory_vectors import fernz_queries, reference_queries
from .v5_walkthrough_cases import GAMES
from .v5_walkthrough_output import fernz_text, reference_text
from .vector_archive import digest


def globals_digest(ram, game, turn):
    base = int.from_bytes(ram[12:14], "big")
    values = bytearray(ram[base : base + 480])
    if game == "murdac" and turn == GAMES[game]["length"]:
        # The reference continues past quit: one spurious turn changes these
        # six globals before its diagnostic. Compare the remaining 234 words.
        for index in (0, 18, 19, 23, 238, 239):
            values[2 * index : 2 * index + 2] = b"\0\0"
    return digest(bytes(values))


def capture(env, original, game, turn, action, response):
    observation, reward, done, info = response
    case = GAMES[game]
    queries = reference_queries(env, original, public_count=case["reference_objects"])
    assert queries["world_count"] == case["objects"]
    assert queries["player"] == case["player"]
    assert queries["max_score"] == case["max_score"]
    raw_queries = queries.copy()
    # Deephome's printed winning ending is missed by the reference's classifier.
    if game == "deephome" and turn == case["length"]:
        assert not queries["victory"] and queries["game_over"]
        queries["victory"] = True
    # A restart menu at a winning ending does not also report a loss.
    if queries["victory"]:
        queries["game_over"] = False
    state = env.get_state()
    halted = game == "murdac" and turn == case["length"]
    info = {key: int(info[key]) for key in ("score", "moves")}
    reference_info = info.copy()
    if halted:
        assert queries["moves"] == info["moves"] == 302
        queries["moves"] = info["moves"] = 301
    if not halted:
        assert int(state[6]) in (0xE4, 0xF6)
    ram = state[0].tobytes()
    a, period, counter = state[7]
    return {
        "action": action,
        "queries": queries,
        "reference_outcomes": {key: raw_queries[key] for key in ("victory", "game_over")},
        "reward": int(reward),
        "reference_done": bool(done),
        "info": info,
        "reference_info": reference_info,
        "halted": halted,
        "input_address": None if halted else int(state[2]) - 1,
        "character_input": False if halted else int(state[6]) == 0xF6,
        "rng": [int(a) & 0x7FFFFFFF, int(period), int(counter) if period else 0],
        "objects": object_fingerprint(ram, object_layout(original)),
        "globals_sha256": globals_digest(ram, game, turn),
        "text_group_end": halted or int(state[6]) != 0xF6 or turn == case["length"],
        "text_sha256": None,
    }, reference_text(observation, game, turn)


def check_step(env, game, turn, record):
    if turn == 0:
        observation = reset_fernz(env, game)
        response = (observation, 0, False, {"score": env.get_score(), "moves": env.get_moves()})
    else:
        response = env.step(record["action"])
        observation = response[0]
    state = env.get_state()
    assert env.done == record["halted"]
    if env.done:
        assert game == "murdac" and turn == GAMES[game]["length"]
        assert state.pc == 0xAB6A and env.story.data[state.pc - 1] == 0xBA  # quit
    if not env.done:
        assert state.input_request.character == record["character_input"]
        assert state.input_request.instruction_address == record["input_address"]
    assert [state.rng.state, state.rng.period, state.rng.position] == record["rng"]
    assert object_fingerprint(state.ram, object_layout(env.story.data)) == record["objects"]
    assert globals_digest(state.ram, game, turn) == record["globals_sha256"]
    expected = record["queries"]
    count = expected["world_count"]
    # Compare the complete enumerated world every turn. Rotate direct lookups
    # as well as checking the player, location and every carried object; asking
    # for every object separately on every turn needlessly repeats count scans.
    direct = {1, count - 1, turn % (count - 1) + 1, expected["player"], expected["location"]}
    direct.update(expected["inventory"])
    queries = fernz_queries(env, direct_objects=None if turn == 0 else direct)
    assert queries == record["queries"], {
        key: (queries[key], record["queries"][key])
        for key in queries
        if queries[key] != record["queries"][key]
    }
    assert response[1] == record["reward"] and response[-1] == record["info"]
    assert env.get_state() == state, "Inspection mutated the checkpoint"
    return observation


def replay_walkthrough(path, game, documents):
    from fernz import FernzEnv

    case = GAMES[game]
    header = documents["manifest.json"]
    assert header["kind"] == "v5-walkthrough" and header["record_version"] == 1
    assert digest(path.read_bytes()) == header["story"]["file_sha256"]
    route = documents["walkthrough.json"]["cases"][0]
    assert route["seed"] == case["seed"] and len(route["steps"]) == case["length"] + 1
    env = FernzEnv(path, seed=case["seed"], **header["geometry"])
    text = []
    checkpoints = {1, case["length"] // 3, 2 * case["length"] // 3, case["length"]}
    try:
        for turn, record in enumerate(route["steps"]):
            before = env.get_state() if turn in checkpoints else None
            try:
                observation = check_step(env, game, turn, record)
                text.append(fernz_text(observation, game, turn))
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
                        assert check_step(fork, game, turn, record) == observation
                        assert fork.get_state() == after
                        assert env.get_state() == after
                    finally:
                        fork.close()
            except (AssertionError, RuntimeError, ValueError) as error:
                error.add_note(f"{game}: walkthrough turn {turn}, action {record['action']!r}")
                raise
        assert not text and env.victory() and not env.game_over()
        final = env.get_state()
        env.reset()
        env.set_state(final)
        assert env.victory() and env.get_state() == final
    finally:
        env.close()


def replay_counters(path, game, document):
    from fernz import FernzEnv

    case = GAMES[game]
    env = FernzEnv(path, seed=case["seed"])
    try:
        reset_fernz(env, game)
        saved = env.get_state()
        base = int.from_bytes(saved.ram[12:14], "big")
        for record in document["cases"][0]["steps"]:
            ram = bytearray(saved.ram)
            address = base + 2 * case[f"{record['field']}_global"]
            ram[address : address + 2] = record["value"].to_bytes(2, "big")
            env.set_state(replace(saved, ram=bytes(ram)))
            before = env.get_state()
            assert (env.get_score(), env.get_moves()) == (record["score"], record["moves"])
            assert env.get_state() == before
    finally:
        env.close()
