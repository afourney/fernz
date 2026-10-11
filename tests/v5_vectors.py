"""Shared V5 assertions and measurements from the public reference API."""

import re

from .v5_queries import query_fingerprint
from .vector_archive import digest


def object_memory(data):
    # The pinned 9:05 build lays out all objects/properties between its object
    # table and global variables. Exclude host capabilities and parser scratch.
    start = int.from_bytes(data[0x0A:0x0C], "big")
    end = int.from_bytes(data[0x0C:0x0E], "big")
    assert start == 0x10A and end == 0x10A5
    return data[start:end]


def reference_observation(observation, *, halted=False):
    observation = observation.replace("\r\n", "\n")
    # Public observations sometimes include the redraw of the upper status
    # window after confirmation input. Match its exact measured geometry.
    status = re.search(r" {128}(Bedroom|Bathroom)Time:  9:\d\d am$", observation)
    if status:
        observation = observation[: status.start()]
        if halted:
            assert observation == "\n>"
            return "", "quit"
        if observation == "\n>":
            return observation, "cancelled"
        assert observation.endswith("? ")
        return observation, "confirmation"
    if observation.endswith("get on?") or observation.endswith("stop here?"):
        return observation, "question"
    if observation.endswith("QUIT"):
        return observation, "ending"
    if observation.endswith("Please give one of the answers above."):
        return observation, "ending-retry"
    return observation, "turn"


def fernz_observation(observation, mode):
    observation = observation.replace("\r\n", "\n")
    assert observation.startswith("\n")
    observation = observation[1:]
    suffixes = {
        "turn": "\n\n>",
        "question": " >> ",
        "ending": "?\n> ",
        "ending-retry": "]\n> ",
    }
    if mode in suffixes:
        suffix = suffixes[mode]
        assert observation.endswith(suffix), (mode, repr(observation[-100:]))
        return observation[: -len(suffix)]
    if mode == "confirmation":
        assert observation.endswith("? ")
    elif mode == "cancelled":
        assert observation == "\n>"
    elif mode == "quit":
        assert observation == ""
    else:
        raise ValueError(f"Unknown V5 observation mode: {mode}")
    return observation


def capture_reference(env, action, observation, *, halted=False):
    text, mode = reference_observation(observation, halted=halted)
    return {
        "action": action,
        "presentation": mode,
        "halted": halted,
        "queries": query_fingerprint(env),
        "observation_sha256": digest(text.encode()),
        "object_memory_sha256": digest(object_memory(env.get_state()[0].tobytes())),
    }


def measure_step(env, action, *, halted=False):
    observation, reward, done, _ = env.step(action)
    record = capture_reference(env, action, observation, halted=halted)
    record.update(reward=int(reward), reference_done=bool(done))
    return record


def check_step(env, record):
    response = env.reset() if record["action"] is None else env.step(record["action"])
    observation = fernz_observation(response[0], record["presentation"])
    assert digest(observation.encode()) == record["observation_sha256"], record["action"]
    assert digest(object_memory(env.get_state().ram)) == record["object_memory_sha256"]
    assert env.done == record["halted"]
    before = env.get_state()
    assert query_fingerprint(env, fernz=True) == record["queries"], record["action"]
    assert env.get_state() == before
    info = {key: record["queries"][key] for key in ("score", "moves")}
    assert response[-1] == info
    if "reward" in record:
        assert response[1] == record["reward"]
        assert record["reference_done"] == (env.game_over() or env.victory())
    return response


def replay_documents(path, documents):
    from fernz import FernzEnv

    from .test_save_restore import Storage
    from .v5_cases import CHECKPOINTS, SEED_905

    assert documents["manifest.json"]["record_version"] == 3
    storage = Storage()
    env = FernzEnv(path, seed=SEED_905, save_handler=storage.save, restore_handler=storage.restore)
    try:
        checkpoints = {}
        for turn, record in enumerate(documents["walkthrough.json"]["cases"][0]["steps"]):
            check_step(env, record)
            if turn in CHECKPOINTS:
                checkpoints[turn] = env.get_state()
        for name, document in documents.items():
            if name in ("manifest.json", "startup.json", "walkthrough.json", "breadth.json"):
                continue
            if name == "seeds.json":
                for case in document["cases"]:
                    env.seed(case["seed"])
                    check_step(env, case["steps"][0])
                    original = env.get_state()
                    fork = env.copy()
                    try:
                        for record in case["steps"][1:]:
                            check_step(fork, record)
                        assert env.get_state() == original
                        fork.reset()
                        assert fork.get_state() == original
                    finally:
                        fork.close()
                continue
            for case in document["cases"]:
                env.set_state(checkpoints[case["checkpoint"]])
                for record in case["steps"]:
                    before = env.get_state()
                    check_step(env, record)
                    after = env.get_state()
                    env.set_state(before)
                    check_step(env, record)
                    assert env.get_state() == after
    finally:
        env.close()
