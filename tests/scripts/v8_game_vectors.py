"""Measure V8 games using only documented public Jericho APIs on Linux."""

from ..v8_cases import BOOT_ACTIONS, SEED, story_identity
from ..v8_vectors import capture
from ..vector_archive import FORMAT_VERSION, REFERENCE_VERSION, digest, json_bytes


def generate_v8(path, game):
    from jericho import FrotzEnv

    original = path.read_bytes()
    assert digest(original) == story_identity(game)["file_sha256"]
    env = FrotzEnv(str(path.resolve()), seed=SEED)
    try:
        observation = env.reset()[0]
        ram = env.get_state()[0]
        geometry = {"screen_width": int(ram[0x21]), "screen_height": int(ram[0x20])}
        documents = {
            "opening.json": {
                "cases": [
                    {
                        "id": "opening",
                        "seed": SEED,
                        "steps": [capture(env, original, game, None, observation)],
                    }
                ]
            }
        }
    finally:
        env.close()
    documents["manifest.json"] = {
        "format_version": FORMAT_VERSION,
        "kind": "v8-game",
        "record_version": 1,
        "story": story_identity(game),
        "boot_actions": list(BOOT_ACTIONS.get(game, ())),
        "geometry": geometry,
        "reference": {
            "name": "Jericho",
            "version": REFERENCE_VERSION,
            "interface": "public Python API",
        },
        "files": {
            name: {
                "sha256": digest(json_bytes(doc)),
                "cases": len(doc["cases"]),
                "records": sum(len(case["steps"]) for case in doc["cases"]),
            }
            for name, doc in documents.items()
        },
    }
    return documents
