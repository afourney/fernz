"""Generate V5 expectations using public Jericho calls, never its source."""

import os
from tempfile import TemporaryDirectory

from ..v5_cases import CHECKPOINTS, DETOURS, SCENARIOS, SEED_905, STARTUP_ACTIONS, STORY_905
from ..v5_vectors import capture_reference
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
        route.append(capture_reference(reference, action, reference.step(action)[0]))
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
                records.append(capture_reference(reference, command, reference.step(command)[0]))
            cases.append({"id": f"detour-{index}", "checkpoint": turn, "steps": records})
        documents[f"detours/{turn}.json"] = {"cases": cases}
    cases = []
    for name, turn, actions in SCENARIOS:
        reference.set_state(checkpoints[turn])
        records = []
        for index, action in enumerate(actions):
            record = capture_reference(
                reference,
                action,
                reference.step(action)[0],
                halted=name == "quit-confirmed" and index == len(actions) - 1,
            )
            records.append(record)
            if name == "loss-and-restart" and index == 0:
                assert reference.game_over() and not reference.victory()
        cases.append({"id": name, "checkpoint": turn, "steps": records})
    documents["scenarios.json"] = {"cases": cases}
    documents["manifest.json"] = {
        "format_version": FORMAT_VERSION,
        "kind": "v5-gameplay",
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
