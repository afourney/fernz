"""Generate full V5 trajectories through public executable behavior only."""

from contextlib import chdir
from tempfile import TemporaryDirectory

from ..v5_trajectory_cases import COMMANDS, DEATHS, GAME_COMMANDS, GAMES, PERSISTENCE_TURN, SEED
from ..v5_trajectory_vectors import capture
from .v5_startup_vectors import manifest, startup_document


def generate_trajectory(path, game):
    from jericho import FrotzEnv

    path = path.resolve()
    original = path.read_bytes()
    documents = {"breadth.json": startup_document(path, game)}
    with TemporaryDirectory(prefix="fernz-v5-route-") as tmp, chdir(tmp):
        env = FrotzEnv(str(path), seed=SEED)
        try:

            def opening():
                observation, info = env.reset()
                return capture(env, original, game, None, (observation, 0, False, info))

            def steps(actions):
                records = []
                for action in actions:
                    # A read_char consumes a key, not a parser command. Avoid
                    # leaving the rest of a word in the reference host queue,
                    # which is outside its public get_state() tuple.
                    if int(env.get_state()[6]) == 0xF6:
                        action = action[:1]
                    record = capture(env, original, game, action, env.step(action))
                    records.append(record)
                    if record["reference_done"]:
                        break
                return records

            route = [opening()]
            checkpoints = {0: env.get_state()}
            actions = env.get_walkthrough()
            assert len(actions) == GAMES[game]["length"]
            for turn, action in enumerate(actions, 1):
                route += steps((action,))
                if turn in GAMES[game]["checkpoints"]:
                    checkpoints[turn] = env.get_state()
            assert env.victory() and env.get_score() == GAMES[game]["winning_score"]
            documents["walkthrough.json"] = {
                "cases": [{"id": "winning-route", "seed": SEED, "steps": route}]
            }
            for turn in GAMES[game]["checkpoints"][:-1]:
                cases = []
                for index, action in enumerate((*COMMANDS, *GAME_COMMANDS[game])):
                    env.set_state(checkpoints[turn])
                    cases.append(
                        {
                            "id": f"detour-{index}",
                            "checkpoint": turn,
                            "steps": steps((action, "look", "inventory")),
                        }
                    )
                documents[f"detours/{turn}.json"] = {"cases": cases}
            turn, actions = DEATHS[game]
            env.set_state(checkpoints[turn])
            loss = steps(actions)
            assert env.game_over() and not env.victory()
            cases = [{"id": "loss", "checkpoint": turn, "steps": loss}]
            turn = PERSISTENCE_TURN[game]
            env.set_state(checkpoints[turn])
            cases.append(
                {
                    "id": "save-restore",
                    "checkpoint": turn,
                    "steps": steps(
                        (
                            "save",
                            "wait",
                            *(("n",) if game == "sherlock" else ()),
                            "inventory",
                            "restore",
                            "look",
                        )
                    ),
                }
            )
            env.set_state(checkpoints[turn])
            # In-game restart leaves the title key pending in both engines.
            restart = steps(
                (
                    "restart",
                    "no",
                    "look",
                    "restart",
                    "yes",
                    *(("",) if game == "sherlock" else ()),
                    "look",
                )
            )
            cases.append({"id": "restart", "checkpoint": turn, "steps": restart})
            documents["scenarios.json"] = {"cases": cases}
            cases = []
            for seed in (1, 42, 1000):
                env.seed(seed)
                records = [
                    opening(),
                    *steps((*env.get_walkthrough()[:10], "wait", "look", "inventory")),
                ]
                cases.append({"id": f"seed-{seed}", "seed": seed, "steps": records})
            documents["seeds.json"] = {"cases": cases}
        finally:
            env.close()
    header = manifest(game, documents)
    header.update(kind="v5-trajectory", seed=SEED, checkpoints=list(GAMES[game]["checkpoints"]))
    documents["manifest.json"] = header
    print(
        f"Recorded {game}: {sum(x['records'] for x in header['files'].values())} boundaries",
        flush=True,
    )
    return documents
