"""Generate V5 expectations using public Jericho calls, never its source."""

from ..v5_cases import SEED_905, STARTUP_ACTIONS, STORY_905
from ..v5_vectors import capture_reference
from ..vector_archive import FORMAT_VERSION, REFERENCE_VERSION, digest, json_bytes


def generate_905(path):
    from jericho import FrotzEnv

    assert digest(path.read_bytes()) == STORY_905["file_sha256"]
    reference = FrotzEnv(str(path), seed=SEED_905)
    try:
        opening = reference.reset()[0]
        assert tuple(reference.get_walkthrough()[:5]) == STARTUP_ACTIONS
        steps = [capture_reference(reference, None, opening)]
        for action in STARTUP_ACTIONS:
            steps.append(capture_reference(reference, action, reference.step(action)[0]))
        documents = {
            "startup.json": {"cases": [{"id": "opening-and-five-commands", "steps": steps}]}
        }
        documents["manifest.json"] = {
            "format_version": FORMAT_VERSION,
            "kind": "v5-startup",
            "story": STORY_905,
            "seed": SEED_905,
            "reference": {
                "name": "Jericho",
                "version": REFERENCE_VERSION,
                "interface": "public Python API",
            },
            "files": {
                name: {"sha256": digest(json_bytes(document)), "cases": 1, "records": len(steps)}
                for name, document in documents.items()
            },
        }
        return documents
    finally:
        reference.close()
