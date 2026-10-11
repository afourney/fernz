"""Measure V8 games using only documented public Jericho APIs on Linux."""

from ..v8_cases import BOOT_ACTIONS, ROUTES, SEED, story_identity
from ..v8_vectors import capture
from ..vector_archive import FORMAT_VERSION, REFERENCE_VERSION, digest, json_bytes
from .v8_walkthrough_vectors import counter_document, walkthrough_document


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
        cases = []
        prefix = env.get_walkthrough()[:12]
        for name, actions in (
            ("walkthrough-prefix", prefix),
            (
                "parser-and-time",
                [
                    *prefix[:5],
                    "look",
                    "inventory",
                    "wait",
                    "wait",
                    "flibbertigibbet",
                    "take unicorn",
                    "open unicorn",
                    "kick door",
                ],
            ),
            ("persistence", [*prefix[:2], "save", "wait", "restore", "look", "inventory"]),
            ("restart", [*prefix[:2], "restart", "no", "look", "restart", "yes"]),
        ):
            records = [capture(env, original, game, None, env.reset()[0])]
            for action in actions:
                if int(env.get_state()[6]) == 0xF6:
                    action = action[:1]
                records.append(capture(env, original, game, action, env.step(action)[0]))
            cases.append({"id": name, "seed": SEED, "steps": records})
        documents["actions.json"] = {"cases": cases}
        if game in ROUTES:
            documents["walkthrough.json"] = walkthrough_document(env, original, game)
            documents["counters.json"] = counter_document(env, game)
    finally:
        env.close()
    documents["manifest.json"] = {
        "format_version": FORMAT_VERSION,
        "kind": "v8-game",
        "record_version": 2,
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
