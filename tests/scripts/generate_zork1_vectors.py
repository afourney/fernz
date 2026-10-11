"""Record public Jericho behavior without reading reference implementation code.

Run on little-endian Linux with the pinned reference group:
    python -m tests.scripts.generate_zork1_vectors [--check]
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
from ..vector_archive import (
    ARCHIVE_PATH,
    FORMAT_VERSION,
    REFERENCE_VERSION,
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
        help="Compare against fresh public reference runs without writing the ZIP",
    )
    parser.add_argument("--output", type=Path, default=ARCHIVE_PATH)
    parser.add_argument("--story", type=Path, help="Use an existing copy of the pinned ROM")
    args = parser.parse_args(argv)
    if sys.platform != "linux" or sys.byteorder != "little" or sys.version_info[:2] != (3, 11):
        parser.error(
            "Regeneration requires little-endian Linux and Python 3.11; replay is portable"
        )
    if version("jericho") != REFERENCE_VERSION:
        parser.error(f"Regeneration requires Jericho {REFERENCE_VERSION}")
    story_path = (args.story or ensure_jericho_games(ROOT / "games") / "zork1.z5").resolve()
    with TemporaryDirectory(prefix="fernz-record-") as tmp, chdir(tmp):
        documents = generate(story_path)
    if args.check:
        existing = read_archive(args.output)
        changed = [
            name
            for name in sorted(existing.keys() | documents.keys())
            if existing.get(name) != documents.get(name)
        ]
        if changed:
            parser.exit(
                1,
                "Stale Zork vectors; investigate before regenerating:\n"
                + "\n".join(changed)
                + "\n",
            )
        print(f"Verified {len(documents)} ZIP members against fresh Jericho runs")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".vectors-", dir=args.output.parent) as tmp:
            staged = Path(tmp) / args.output.name
            write_archive(staged, documents)
            staged.replace(args.output)
        print(
            f"Wrote {args.output}: {len(documents)} members, {args.output.stat().st_size:,} bytes"
        )


if __name__ == "__main__":
    main()
