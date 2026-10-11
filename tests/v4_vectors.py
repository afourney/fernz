"""V4 comparisons shared by live Jericho tests and portable vector replay."""

from dataclasses import replace

from fernz import FernzEnv

from .observation_helpers import join_observations
from .test_save_restore import Storage
from .v4_cases import CHECKPOINTS, COUNTERS, ROUTE_LENGTH, SEED, story_identity
from .v5_trajectory_vectors import fernz_queries, reference_queries
from .vector_archive import digest


def text_content(text, *, opening=False, fernz=False):
    if fernz:
        text = text.text
        if opening:
            # Public reset clips one leading space of Trinity's title display.
            assert text.startswith(" ")
            text = text[1:]
        text = text.removesuffix(">")
    # Compare both windows, including boxed quotations. Only whitespace and
    # the independently measured final command prompt differ in presentation.
    return " ".join(text.replace("\r\n", "\n").split())


def reset_fernz(env):
    observation, _ = env.reset()
    assert env.get_state().input_request.character
    continuation = env.step("")
    assert not hasattr(env.get_state().input_request, "store")
    return join_observations(observation, continuation[0]), 0, False, continuation[-1]


def capture(env, original, action, response):
    observation, reward, done, info = response
    state = env.get_state()
    assert int(state[6]) in (0xE4, 0xF6)
    queries = reference_queries(env, original)
    assert queries["world_count"] == 594 and queries["player"] == 103
    assert queries["max_score"] == 100
    outcomes = {key: queries[key] for key in ("game_over", "victory")}
    if queries["victory"]:
        queries["game_over"] = False  # Fernz distinguishes victory from loss.
    a, period, counter = state[7]
    return {
        "action": action,
        "text_sha256": digest(text_content(observation).encode()),
        "ram_sha256": digest(state[0][64:].tobytes()),
        "input_address": int(state[2]) - 1,
        "character_input": int(state[6]) == 0xF6,
        "rng": [int(a) & 0x7FFFFFFF, int(period), int(counter) if period else 0],
        "queries": queries,
        "reference_outcomes": outcomes,
        "reference_done": bool(done),
        "reward": int(reward),
        "info": {key: int(info[key]) for key in ("score", "moves")},
    }


def check_step(env, record):
    response = reset_fernz(env) if record["action"] is None else env.step(record["action"])
    state = env.get_state()
    assert not env.done
    assert state.input_request.instruction_address == record["input_address"]
    assert bool(getattr(state.input_request, "character", False)) == record["character_input"]
    assert [state.rng.state, state.rng.period, state.rng.position] == record["rng"]
    # Every dynamic byte outside the interpreter-owned header is checked,
    # including parser buffers, object/property tables, globals and game scratch.
    assert digest(state.ram[64:]) == record["ram_sha256"]
    expected = record["queries"]
    direct = {1, 593, expected["player"], expected["location"], *expected["inventory"]}
    queries = fernz_queries(env, direct_objects=None if record["action"] is None else direct)
    assert queries == expected, {
        key: (queries[key], expected[key]) for key in queries if queries[key] != expected[key]
    }
    assert env.get_state() == state, "Inspection changed a checkpoint"
    assert response[1] == record["reward"] and response[-1] == record["info"]
    assert record["reference_done"] == (expected["game_over"] or expected["victory"])
    text = text_content(response[0], opening=record["action"] is None, fernz=True)
    assert digest(text.encode()) == record["text_sha256"], (record["action"], text)
    return response


def replay_step(env, record):
    before = env.get_state()
    response = check_step(env, record)
    after = env.get_state()
    env.set_state(before)
    assert check_step(env, record) == response
    assert env.get_state() == after


def replay(path, documents, *, smoke=False):
    manifest = documents["manifest.json"]
    assert manifest["story"] == story_identity()
    assert digest(path.read_bytes()) == manifest["story"]["file_sha256"]
    storage = Storage()
    env = FernzEnv(
        path,
        seed=SEED,
        **manifest["geometry"],
        save_handler=storage.save,
        restore_handler=storage.restore,
    )
    try:
        records = documents["walkthrough.json"]["cases"][0]["steps"]
        assert len(records) in ((6, ROUTE_LENGTH + 1) if smoke else (ROUTE_LENGTH + 1,))
        checkpoints = {}
        for turn, record in enumerate(records[:6] if smoke else records):
            try:
                if turn:
                    replay_step(env, record)
                else:
                    check_step(env, record)
                if turn in CHECKPOINTS:
                    checkpoints[turn] = env.get_state()
            except (AssertionError, RuntimeError, ValueError) as error:
                error.add_note(f"Trinity walkthrough turn {turn}, {record['action']!r}")
                raise
        if smoke:
            return
        assert env.victory() and not env.game_over() and not env.done
        assert env.get_score() == 100 and env.get_moves() == 608
        final = env.get_state()
        reset_fernz(env)
        assert not env.victory()
        env.set_state(final)
        assert env.victory() and env.get_state() == final
        for filename in ("detours.json", "lifecycle.json", "death.json", "seeds.json"):
            for case in documents[filename]["cases"]:
                env.seed(case["seed"])
                if case.get("checkpoint") is not None:
                    env.set_state(checkpoints[case["checkpoint"]])
                for turn, record in enumerate(case["steps"]):
                    try:
                        if record["action"] is None:
                            check_step(env, record)
                        else:
                            replay_step(env, record)
                    except (AssertionError, RuntimeError, ValueError) as error:
                        error.add_note(
                            f"Trinity {filename}, {case['id']}, turn {turn}, {record['action']!r}"
                        )
                        raise
                if filename == "death.json":
                    assert env.game_over() and not env.victory()
        assert storage.saves and storage.restores
        # A copied environment can branch from a midgame snapshot independently.
        env.set_state(checkpoints[300])
        before = env.get_state()
        fork = env.copy()
        try:
            assert check_step(fork, records[301]) == check_step(env, records[301])
            assert fork.get_state() == env.get_state()
            original_after = env.get_state()
            fork.set_state(before)
            fork.step("wait")
            assert env.get_state() == original_after
            assert env.get_state() != fork.get_state()
        finally:
            fork.close()
        reset_fernz(env)
        saved = env.get_state()
        base = int.from_bytes(saved.ram[12:14], "big")
        for record in documents["counters.json"]["cases"][0]["steps"]:
            ram = bytearray(saved.ram)
            address = base + 2 * COUNTERS[record["field"]]
            ram[address : address + 2] = record["value"].to_bytes(2, "big")
            env.set_state(replace(saved, ram=bytes(ram)))
            assert (env.get_score(), env.get_moves()) == (record["score"], record["moves"])
    finally:
        env.close()
