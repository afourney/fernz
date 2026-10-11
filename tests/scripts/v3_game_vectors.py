"""Generate each additional V3 archive from public reference behavior."""

from ..v3_cases import (
    BOOT_ACTIONS,
    COMMANDS,
    DEATHS,
    EXTRA_ROUTES,
    GAME_COMMANDS,
    GAMES,
    LOSS_CONTINUATIONS,
    MECHANICS,
    SEED_FOLLOWUPS,
    SEED_PREFIX_LENGTH,
    SEEDS,
    checkpoint_turns,
    lifecycle_actions,
)
from ..v3_reference import Reference
from ..vector_archive import FORMAT_VERSION, REFERENCE_VERSION, digest, json_bytes


def steps(reference, actions, *, stop_on_outcome=True):
    result = []
    for action in actions:
        record = reference.step(action)
        result.append(record)
        if record["halted"] or (record["done"] and stop_on_outcome):
            break
    return result


def generate_v3(path, game):
    documents = {}
    reference = Reference(path, game)
    try:
        actions = reference.env.get_walkthrough()
        assert len(actions) == GAMES[game]["walkthrough_length"]
        wanted = {
            *checkpoint_turns(game),
            DEATHS[game][0],
            *(turn for _, turn, _ in MECHANICS.get(game, ())),
        }
        checkpoints = {0: reference.env.get_state()}
        route = [reference.opening()]
        for turn, action in enumerate(actions, 1):
            route.append(reference.step(action))
            if turn in wanted:
                checkpoints[turn] = reference.env.get_state()
        assert reference.env.victory()
        assert reference.env.get_score() == reference.env.get_max_score()
        documents["walkthrough.json"] = {
            "cases": [{"id": "walkthrough", "seed": reference.seed, "steps": route}]
        }
        for turn in checkpoint_turns(game):
            cases = []
            for group, commands in (("common", COMMANDS), ("game", GAME_COMMANDS[game])):
                for index, action in enumerate(commands):
                    reference.env.set_state(checkpoints[turn])
                    cases.append(
                        {
                            "id": f"{group}:{index}",
                            "checkpoint": turn,
                            "steps": steps(reference, (action, "look", "inventory")),
                        }
                    )
            documents[f"detours/{turn}.json"] = {"cases": cases}
        scenarios = []
        for name, turn, actions in MECHANICS.get(game, ()):
            reference.env.set_state(checkpoints[turn])
            scenarios.append(
                {
                    "id": name,
                    "checkpoint": turn,
                    "steps": steps(reference, actions, stop_on_outcome=False),
                }
            )
        turn, actions = DEATHS[game]
        reference.env.set_state(checkpoints[turn])
        loss = steps(reference, actions)
        assert loss[-1]["queries"]["game_over"] and not loss[-1]["queries"]["victory"]
        loss.extend(
            steps(
                reference,
                LOSS_CONTINUATIONS.get(game, ("look", "inventory")),
                stop_on_outcome=False,
            )
        )
        scenarios.append({"id": "loss-and-continuation", "checkpoint": turn, "steps": loss})
        turn = checkpoint_turns(game)[1]
        reference.env.set_state(checkpoints[turn])
        lifecycle = lifecycle_actions(game)
        scenarios.append(
            {
                "id": "save-restore-restart",
                "checkpoint": turn,
                "steps": steps(reference, lifecycle, stop_on_outcome=False),
            }
        )
        documents["scenarios.json"] = {"cases": scenarios}
    finally:
        reference.close()
    cases = []
    for seed in (*SEEDS, *EXTRA_ROUTES.get(game, ())):
        reference = Reference(path, game, seed)
        try:
            complete = seed in EXTRA_ROUTES.get(game, ())
            count = len(route) if complete else 1 + SEED_PREFIX_LENGTH.get(game, 10)
            actions = [record["action"] for record in route[1:count]]
            followups = (
                () if complete else SEED_FOLLOWUPS.get(game, (*("wait",) * 5, "look", "inventory"))
            )
            cases.append(
                {
                    "id": f"seed-{seed}",
                    "complete_route": complete,
                    "seed": seed,
                    "steps": [
                        reference.opening(),
                        *steps(reference, (*actions, *followups)),
                    ],
                }
            )
            if complete:
                assert (
                    reference.env.victory()
                    and reference.env.get_score() == GAMES[game]["max_score"]
                )
        finally:
            reference.close()
    documents["seeds.json"] = {"cases": cases}
    documents["manifest.json"] = {
        "format_version": FORMAT_VERSION,
        "kind": "v3-gameplay",
        "game": game,
        "story": GAMES[game],
        "boot_actions": list(BOOT_ACTIONS.get(game, ())),
        "state_format_version": 2,
        "seed": GAMES[game]["seed"],
        "reference": {
            "name": "Jericho",
            "version": REFERENCE_VERSION,
            "platform": "linux",
            "python": "3.11",
            "byteorder": "little",
            "screen_flags1": 16,
        },
        "checkpoints": sorted(wanted),
        "files": {
            name: {
                "sha256": digest(json_bytes(document)),
                "cases": len(document["cases"]),
                "records": sum(len(case["steps"]) for case in document["cases"]),
            }
            for name, document in sorted(documents.items())
        },
    }
    print(
        f"Recorded {game}: {sum(item['records'] for item in documents['manifest.json']['files'].values())} boundaries",
        flush=True,
    )
    return documents
