"""Record every retained V5 startup through documented public Jericho APIs."""

from ..v5_corpus import BOOT_ACTIONS, COMMANDS, SEED, story_identity
from ..v5_corpus_vectors import capture, object_layout
from ..vector_archive import FORMAT_VERSION, REFERENCE_VERSION, digest, json_bytes


def startup_document(path, game):
    from jericho import FrotzEnv

    assert digest(path.read_bytes()) == story_identity(game)["file_sha256"]
    layout = object_layout(path.read_bytes())
    env = FrotzEnv(str(path.resolve()), seed=SEED)
    try:
        cases = []
        for name, commands in (
            ("parser-and-time", COMMANDS),
            ("walkthrough-prefix", tuple(env.get_walkthrough()[:5])),
        ):
            assert len(commands) == 5
            records = [capture(env, game, layout, None, env.reset()[0])]
            for action in commands:
                records.append(capture(env, game, layout, action, env.step(action)[0]))
            cases.append({"id": name, "seed": SEED, "steps": records})
        return {"cases": cases}
    finally:
        env.close()


def manifest(game, documents):
    return {
        "format_version": FORMAT_VERSION,
        "kind": "v5-startup",
        "record_version": 1,
        "game": game,
        "story": story_identity(game),
        "boot_actions": list(BOOT_ACTIONS.get(game, ())),
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


def generate_startup(path, game):
    documents = {"breadth.json": startup_document(path, game)}
    documents["manifest.json"] = manifest(game, documents)
    return documents
