"""Generate V5 expectations using public Jericho calls, never its source."""

import os
from tempfile import TemporaryDirectory

from ..v5_cases import CHECKPOINTS, DETOURS, SCENARIOS, SEED_905, STARTUP_ACTIONS, STORY_905
from ..v5_vectors import capture_reference, measure_step
from ..vector_archive import FORMAT_VERSION, REFERENCE_VERSION, digest, json_bytes


def generate_905(path):
    from jericho import FrotzEnv

    path = path.resolve()
    assert digest(path.read_bytes()) == STORY_905["file_sha256"]
    previous = os.getcwd()
    with TemporaryDirectory(prefix="fernz-v5-reference-") as directory:
        os.chdir(directory)
        reference = FrotzEnv(str(path), seed=SEED_905)
        try:
            return _record_905(reference)
        finally:
            reference.close()
            os.chdir(previous)


def _record_905(reference):
    opening = reference.reset()[0]
    actions = reference.get_walkthrough()
    assert len(actions) == 22 and tuple(actions[:5]) == STARTUP_ACTIONS
    checkpoints = {0: reference.get_state()}
    route = [capture_reference(reference, None, opening)]
    for turn, action in enumerate(actions, 1):
        route.append(measure_step(reference, action))
        if turn in CHECKPOINTS:
            checkpoints[turn] = reference.get_state()
    assert reference.victory() and reference.get_score() == 1
    documents = {
        "startup.json": {"cases": [{"id": "opening-and-five-commands", "steps": route[:6]}]},
        "walkthrough.json": {"cases": [{"id": "winning-route", "steps": route}]},
    }
    for turn in CHECKPOINTS[:4]:
        cases = []
        for index, action in enumerate(DETOURS):
            reference.set_state(checkpoints[turn])
            records = []
            for command in (action, "look", "inventory"):
                records.append(measure_step(reference, command))
            cases.append({"id": f"detour-{index}", "checkpoint": turn, "steps": records})
        documents[f"detours/{turn}.json"] = {"cases": cases}
    cases = []
    for name, turn, actions in SCENARIOS:
        reference.set_state(checkpoints[turn])
        records = []
        for index, action in enumerate(actions):
            record = measure_step(
                reference,
                action,
                halted=name == "quit-confirmed" and index == len(actions) - 1,
            )
            records.append(record)
            if name == "loss-and-restart" and index == 0:
                assert reference.game_over() and not reference.victory()
        cases.append({"id": name, "checkpoint": turn, "steps": records})
    documents["scenarios.json"] = {"cases": cases}
    cases = []
    for seed in (1, 42, 1000, 2**31 - 1):
        assert reference.seed(seed) == seed
        records = [capture_reference(reference, None, reference.reset()[0])]
        for action in reference.get_walkthrough()[:11]:
            records.append(measure_step(reference, action))
        cases.append({"id": f"seed-{seed}", "seed": seed, "steps": records})
    documents["seeds.json"] = {"cases": cases}
    documents["manifest.json"] = {
        "format_version": FORMAT_VERSION,
        "kind": "v5-gameplay",
        "record_version": 3,
        "story": STORY_905,
        "seed": SEED_905,
        "reference": {
            "name": "Jericho",
            "version": REFERENCE_VERSION,
            "interface": "public Python API",
        },
        "files": {
            name: {
                "sha256": digest(json_bytes(document)),
                "cases": len(document["cases"]),
                "records": sum(len(case["steps"]) for case in document["cases"]),
            }
            for name, document in documents.items()
        },
    }
    return documents
