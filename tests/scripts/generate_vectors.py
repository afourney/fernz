"""Record retained-story behavior and metadata in portable ZIP archives.

Run on little-endian Linux with the pinned reference group:
    python -m tests.scripts.generate_vectors [--check]

Use --only storyfiles on any platform without the reference dependency.
"""

import argparse
import sys
from contextlib import chdir
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

from fernz import Story

from ..game_files import ensure_jericho_games
from ..state_bridge import StateBridge
from ..v3_cases import GAMES as V3_GAMES
from ..v3_cases import selected_games
from ..v5_corpus import GAMES as V5_GAMES
from ..v5_shards import selected_games as selected_v5_games
from ..v8_cases import GAMES as V8_GAMES
from ..vector_archive import (
    ARCHIVE_PATH,
    FORMAT_VERSION,
    REFERENCE_VERSION,
    STORYFILES_PATH,
    digest,
    json_bytes,
    query_fingerprint,
    read_archive,
    state_fingerprint,
    write_archive,
)
from ..zork_scenarios import (
    CELLAR_DEATH_ACTIONS,
    CHECKPOINTS,
    COMBAT_ACTIONS,
    COMBAT_SEEDS,
    COMMAND_GROUPS,
    SCENARIOS,
    WALKTHROUGH_SEED,
    ZORK1_SHA256,
)
from .lgop_vectors import generate_lgop
from .storyfile_vectors import generate_storyfiles
from .v3_game_vectors import generate_v3
from .v4_game_vectors import generate_v4
from .v5_game_vectors import generate_905
from .v5_trajectory_vectors import generate_trajectory
from .v5_walkthrough_vectors import generate_walkthrough
from .v8_game_vectors import generate_v8

ROOT = Path(__file__).resolve().parents[2]


class Recorder:
    def __init__(self, env, story, seed):
        self.env = env
        self.opening = env.reset()
        self.bridge = StateBridge(story, env.get_state(), seed=seed)

    def capture(self, action, response, *, mode="turn"):
        observation, reward, done, info = response
        halted = mode == "ending"
        return {
            "action": action,
            "observation_mode": mode,
            "observation_sha256": digest(observation.replace("\r\n", "\n").encode()),
            "reward": int(reward),
            "done": bool(done),
            "info": {key: int(info[key]) for key in ("score", "moves")},
            "queries": query_fingerprint(self.env),
            # The measured bridge supports pending input, not a halted VM.
            # Never turn the reference's stale read register into a fake state.
            "state": None
            if halted
            else state_fingerprint(self.bridge.from_jericho(self.env.get_state())),
        }

    def opening_record(self):
        observation, info = self.opening
        return self.capture(None, (observation, 0, False, info), mode="opening")

    def step(self, action, *, mode="turn"):
        return self.capture(action, self.env.step(action), mode=mode)


def generate(story_path):
    # This import is deliberately local. Portable readers require neither
    # Jericho nor NumPy; a missing reference on Linux is an error, never a skip.
    from jericho import FrotzEnv

    story = Story.from_file(story_path)
    if digest(story_path.read_bytes()) != ZORK1_SHA256 or story.header.version != 3:
        raise ValueError("Unexpected Zork I story; do not regenerate against a different ROM")
    documents = {}

    def add(name, cases):
        documents[name + ".json"] = {"cases": cases}
        print(f"Recorded {name}: {sum(len(case['steps']) for case in cases)} states", flush=True)

    reference = FrotzEnv(str(story_path), seed=WALKTHROUGH_SEED)
    try:
        recorder = Recorder(reference, story, WALKTHROUGH_SEED)
        actions = reference.get_walkthrough()
        assert reference.seed() == WALKTHROUGH_SEED and len(actions) == 396
        checkpoints = {}
        by_turn = {turn: name for name, (turn, _) in CHECKPOINTS.items()}
        steps = [recorder.opening_record()]
        checkpoints[by_turn[0]] = reference.get_state()
        for turn, action in enumerate(actions, 1):
            steps.append(recorder.step(action, mode="ending" if turn == len(actions) else "turn"))
            if turn in by_turn:
                name = by_turn[turn]
                assert reference.get_player_location().num == CHECKPOINTS[name][1]
                checkpoints[name] = reference.get_state()
        assert reference.victory() and reference.get_score() == 350
        add("walkthrough", [{"id": "walkthrough", "seed": WALKTHROUGH_SEED, "steps": steps}])

        for checkpoint in CHECKPOINTS:
            cases = []
            for group, commands in COMMAND_GROUPS.items():
                for action in commands:
                    reference.set_state(checkpoints[checkpoint])
                    cases.append(
                        {
                            "id": f"{group}:{action or '<empty>'}",
                            "checkpoint": checkpoint,
                            "steps": [
                                recorder.step(command) for command in (action, "look", "inventory")
                            ],
                        }
                    )
            add(f"detours/{checkpoint}", cases)

        for scenario in SCENARIOS:
            reference.set_state(checkpoints[scenario.checkpoint])
            add(
                f"scenarios/{scenario.id}",
                [
                    {
                        "id": scenario.id,
                        "checkpoint": scenario.checkpoint,
                        "steps": [recorder.step(action) for action in scenario.actions],
                    }
                ],
            )

        reference.set_state(checkpoints["living-room"])
        add(
            "scenarios/cellar-death",
            [
                {
                    "id": "cellar-death",
                    "checkpoint": "living-room",
                    "steps": [recorder.step(action) for action in CELLAR_DEATH_ACTIONS],
                }
            ],
        )

        # Public SAVE/RESTORE uses Jericho's default path. The caller supplies
        # a temporary working directory; no saved-game bytes enter the ZIP.
        reference.set_state(checkpoints["torch-room"])
        lifecycle = (
            "save",
            "look",
            "restart",
            "no",
            "restart",
            "yes",
            "restore",
            "look",
            "inventory",
        )
        add(
            "scenarios/save-restore-restart",
            [
                {
                    "id": "save-restore-restart",
                    "checkpoint": "torch-room",
                    "steps": [
                        recorder.step(
                            action, mode="restart-confirmation" if action == "restart" else "turn"
                        )
                        for action in lifecycle
                    ],
                }
            ],
        )
    finally:
        reference.close()

    cases = []
    for seed in COMBAT_SEEDS:
        reference = FrotzEnv(str(story_path), seed=seed)
        try:
            recorder = Recorder(reference, story, seed)
            cases.append(
                {
                    "id": f"combat-seed-{seed}",
                    "seed": seed,
                    "steps": [
                        recorder.opening_record(),
                        *[recorder.step(action) for action in COMBAT_ACTIONS],
                    ],
                }
            )
        finally:
            reference.close()
    add("combat", cases)
    documents["manifest.json"] = {
        "format_version": FORMAT_VERSION,
        "state_format_version": 2,
        "story": {"filename": "zork1.z5", "version": 3, "sha256": ZORK1_SHA256},
        "reference": {
            "name": "Jericho",
            "version": REFERENCE_VERSION,
            "platform": "linux",
            "python": "3.11",
            "byteorder": "little",
        },
        "seed": WALKTHROUGH_SEED,
        "checkpoints": {
            name: {"turn": turn, "location": location}
            for name, (turn, location) in CHECKPOINTS.items()
        },
        "files": {
            name: {
                "sha256": digest(json_bytes(document)),
                "cases": len(document["cases"]),
                "records": sum(len(case["steps"]) for case in document["cases"]),
            }
            for name, document in sorted(documents.items())
        },
    }
    return documents


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare selected archives against fresh measurements without writing",
    )
    parser.add_argument(
        "--only",
        choices=(
            "zork1",
            "storyfiles",
            "v3",
            "lgop",
            "v4",
            "trinity",
            "v5",
            "v8",
            *V3_GAMES,
            *V5_GAMES,
            *V8_GAMES,
        ),
        help="Limit recording/checking to one archive or a version group (default: all)",
    )
    parser.add_argument("--output", type=Path, default=ARCHIVE_PATH)
    parser.add_argument("--storyfiles-output", type=Path, default=STORYFILES_PATH)
    parser.add_argument("--suite", type=Path, help="Use an existing retained-story suite directory")
    parser.add_argument("--story", type=Path, help="Use an existing copy of the pinned ROM")
    parser.add_argument("--v3-shard", help="Select a disjoint V3 group, e.g. 1/3")
    parser.add_argument("--v5-shard", help="Select a disjoint V5 group, e.g. 1/3")
    parser.add_argument("--output-dir", type=Path, default=ARCHIVE_PATH.parent)
    args = parser.parse_args(argv)
    try:
        games = selected_games(args.v3_shard)
        v5_games = selected_v5_games(args.v5_shard)
    except ValueError as error:
        parser.error(str(error))
    if args.only is None and args.output.resolve() == args.storyfiles_output.resolve():
        parser.error("The Zork and storyfiles archives need distinct output paths")
    if args.only != "storyfiles":
        if sys.platform != "linux" or sys.byteorder != "little" or sys.version_info[:2] != (3, 11):
            parser.error(
                "Zork regeneration requires little-endian Linux and Python 3.11; replay is portable"
            )
        if version("jericho") != REFERENCE_VERSION:
            parser.error(f"Zork regeneration requires Jericho {REFERENCE_VERSION}")
    suite = args.suite
    if suite is None and (args.only != "zork1" or args.story is None):
        suite = ensure_jericho_games(ROOT / "games")
    archives = {}
    if args.only in (None, "storyfiles"):
        archives[args.storyfiles_output] = generate_storyfiles(suite)
    if args.only in (None, "zork1"):
        story_path = (args.story or suite / "zork1.z5").resolve()
        with TemporaryDirectory(prefix="fernz-record-") as tmp, chdir(tmp):
            archives[args.output] = generate(story_path)
    if args.only in (None, "v3", "lgop", *V3_GAMES):
        for game in games:
            if args.only not in (None, "v3") and game != args.only:
                continue
            filename = "lgop.z3" if game == "lgop" else V3_GAMES[game]["filename"]
            path = (suite / filename).resolve()
            with TemporaryDirectory(prefix="fernz-record-") as tmp, chdir(tmp):
                archives[args.output_dir / f"{game}_vectors.zip"] = (
                    generate_lgop(path) if game == "lgop" else generate_v3(path, game)
                )
    if args.only in (None, "v4", "trinity"):
        path = (suite / "trinity.z4").resolve()
        with TemporaryDirectory(prefix="fernz-record-") as tmp, chdir(tmp):
            archives[args.output_dir / "trinity_vectors.zip"] = generate_v4(path)
    if args.only in (None, "905") and "905" in v5_games:
        path = (suite / "905.z5").resolve()
        with TemporaryDirectory(prefix="fernz-record-") as tmp, chdir(tmp):
            archives[args.output_dir / "905_vectors.zip"] = generate_905(path)
    if args.only in (None, "v5", *V5_GAMES):
        for game in v5_games:
            if args.only in V5_GAMES and game != args.only:
                continue
            path = (suite / f"{game}.z5").resolve()
            if game == "905":
                if args.only == "v5":
                    archives[args.output_dir / "905_vectors.zip"] = generate_905(path)
            else:
                generator = (
                    generate_trajectory
                    if game in ("balances", "sherlock")
                    else generate_walkthrough
                )
                archives[args.output_dir / f"{game}_vectors.zip"] = generator(path, game)
    if args.only in (None, "v8", *V8_GAMES):
        for game in V8_GAMES:
            if args.only in V8_GAMES and game != args.only:
                continue
            path = (suite / f"{game}.z8").resolve()
            with TemporaryDirectory(prefix="fernz-record-") as tmp, chdir(tmp):
                archives[args.output_dir / f"{game}_vectors.zip"] = generate_v8(path, game)
    changed = []
    for path, documents in archives.items():
        if args.check:
            existing = read_archive(path)
            changed.extend(
                f"{path.name}: {name}"
                for name in sorted(existing.keys() | documents.keys())
                if existing.get(name) != documents.get(name)
            )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix=".vectors-", dir=path.parent) as tmp:
                staged = Path(tmp) / path.name
                write_archive(staged, documents)
                staged.replace(path)
            print(f"Wrote {path}: {len(documents)} members, {path.stat().st_size:,} bytes")
    if args.check:
        if changed:
            parser.exit(
                1,
                "Stale vectors; investigate before regenerating:\n" + "\n".join(changed) + "\n",
            )
        for path, documents in archives.items():
            print(f"Verified {path.name}: {len(documents)} members against fresh measurements")


if __name__ == "__main__":
    main()
