"""Measure Trinity using only the documented public Jericho API on Linux."""

from ..v4_cases import CHECKPOINTS, COMMANDS, COUNTERS, ROUTE_LENGTH, SEED, story_identity
from ..v4_vectors import capture
from ..vector_archive import FORMAT_VERSION, REFERENCE_VERSION, digest, json_bytes


def generate_v4(path, *, smoke=False):
    from jericho import FrotzEnv

    original = path.read_bytes()
    assert digest(original) == story_identity()["file_sha256"]
    env = FrotzEnv(str(path.resolve()), seed=SEED)
    try:

        def opening():
            observation, info = env.reset()
            return capture(env, original, None, (observation, 0, False, info))

        def steps(actions, *, stop_on_outcome=True):
            records = []
            for action in actions:
                records.append(capture(env, original, action, env.step(action)))
                if stop_on_outcome and (env.game_over() or env.victory()):
                    break
            return records

        first = opening()
        ram = env.get_state()[0]
        geometry = {"screen_width": int(ram[0x21]), "screen_height": int(ram[0x20])}
        actions = env.get_walkthrough()
        assert len(actions) == ROUTE_LENGTH
        checkpoints = {0: env.get_state()}
        route = [first]
        for turn, action in enumerate(actions[:5] if smoke else actions, 1):
            route.extend(steps((action,)))
            if turn in CHECKPOINTS:
                checkpoints[turn] = env.get_state()
        documents = {
            "walkthrough.json": {"cases": [{"id": "winning-route", "seed": SEED, "steps": route}]}
        }
        if not smoke:
            assert env.victory() and env.get_score() == 100 and env.get_moves() == 608
            cases = []
            for checkpoint in CHECKPOINTS:
                for number, command in enumerate(COMMANDS):
                    env.set_state(checkpoints[checkpoint])
                    cases.append(
                        {
                            "id": f"{checkpoint}:{number}",
                            "checkpoint": checkpoint,
                            "seed": SEED,
                            "steps": steps((command, "look", "inventory")),
                        }
                    )
            documents["detours.json"] = {"cases": cases}
            cases = []
            for checkpoint in (0, 150, 450):
                env.set_state(checkpoints[checkpoint])
                cases.append(
                    {
                        "id": f"storage:{checkpoint}",
                        "checkpoint": checkpoint,
                        "seed": SEED,
                        "steps": steps(("save", "wait", "restore", "look", "inventory")),
                    }
                )
            env.set_state(checkpoints[150])
            cases.append(
                {
                    "id": "restart",
                    "checkpoint": 150,
                    "seed": SEED,
                    "steps": steps(("restart", "no", "look", "restart", "yes", "", "look")),
                }
            )
            documents["lifecycle.json"] = {"cases": cases}
            first = opening()
            death = [first, *steps(["wait"] * 36)]
            assert len(death) == 37 and env.game_over() and not env.victory()
            documents["death.json"] = {
                "cases": [{"id": "wait-for-disaster", "seed": SEED, "steps": death}]
            }
            cases = []
            for seed in (1, 42, 1000):
                assert env.seed(seed) == seed
                cases.append(
                    {"id": f"seed:{seed}", "seed": seed, "steps": [opening(), *steps(actions[:50])]}
                )
            documents["seeds.json"] = {"cases": cases}
            env.seed(SEED)
            env.reset()
            state = env.get_state()
            ram = state[0]
            base = int.from_bytes(ram[12:14].tobytes(), "big")
            counters = []
            for field, global_number in COUNTERS.items():
                for value in (0, 1, 255, 256, 32767, 32768, 65535):
                    changed = ram.copy()
                    address = base + 2 * global_number
                    changed[address : address + 2] = list(value.to_bytes(2, "big"))
                    env.set_state((changed, *state[1:]))
                    counters.append(
                        {
                            "field": field,
                            "value": value,
                            "score": int(env.get_score()),
                            "moves": int(env.get_moves()),
                        }
                    )
            documents["counters.json"] = {
                "cases": [{"id": "counter-widths", "seed": SEED, "steps": counters}]
            }
    finally:
        env.close()
    documents["manifest.json"] = {
        "format_version": FORMAT_VERSION,
        "kind": "v4-game",
        "record_version": 1,
        "story": story_identity(),
        "geometry": geometry,
        "boot_actions": [""],
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
