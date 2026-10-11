"""Record LGOP via public execution/snapshots; Jericho has no LGOP query binding."""

from dataclasses import replace

from fernz import Story

from ..lgop_cases import (
    CHECKPOINTS,
    COMMANDS,
    LOSS_HASH,
    PLAYER,
    SEED,
    STORY,
    WIN_HASH,
    partial_routes,
    walkthrough,
)
from ..state_bridge import StateBridge
from ..v3_oracle import object_count, object_records, word
from ..v3_vectors import reference_text, status_display
from ..vector_archive import (
    FORMAT_VERSION,
    REFERENCE_VERSION,
    digest,
    json_bytes,
    state_fingerprint,
)


class Recorder:
    def __init__(self, path, seed=SEED):
        from jericho import FrotzEnv

        self.seed = seed
        self.story = Story.from_file(path)
        assert digest(path.read_bytes()) == STORY["file_sha256"]
        self.env = FrotzEnv(str(path), seed=seed)
        self.env.reset()
        self.capabilities()
        self.bridge = StateBridge(self.story, self.env.get_state(), seed=seed)
        self.texts = []
        self.previous_score = 0

    def capabilities(self):
        native = self.env.get_state()
        ram = native[0].copy()
        ram[1] = (int(ram[1]) & ~0x70) | 0x30
        self.env.set_state((ram, *native[1:]))

    def world(self):
        ram = self.env.get_state()[0].tobytes()
        data = ram + self.story.data[len(ram) : self.story.size]
        return object_records(data, object_count(self.story.data))

    def restore(self, state):
        # The public snapshot does not include the frontend's pending word.
        # Reach a known ordinary prompt before restoring an ordinary checkpoint.
        self.env.reset()
        self.env.step("")
        self.env.set_state(state)
        ram = state[0].tobytes()
        self.previous_score = int.from_bytes(
            ram[word(ram, 12) + 2 : word(ram, 12) + 4], "big", signed=True
        )

    def capture(self, action):
        if action is None:
            observation = self.env.reset()[0]
            self.previous_score = 0
        else:
            observation = self.env.step(action)[0]
        self.capabilities()
        native = self.env.get_state()
        ram = native[0].tobytes()
        world = self.world()
        assert len(world) == STORY["world_count"]
        text = (
            reference_text(observation, (obj["name"] for obj in world))
            .removeprefix(" >")
            .removeprefix(">")
        )
        self.texts.append(text)
        hashes = {digest(" ".join(line.split()).encode()) for line in text.splitlines()}
        victory = WIN_HASH in hashes
        loss = LOSS_HASH in hashes and not victory
        base = word(ram, 12)
        score = int.from_bytes(ram[base + 2 : base + 4], "big", signed=True)
        moves = word(ram, base + 4)
        player = world[PLAYER]
        parent = player["parent"]
        inventory = []
        number = player["child"]
        while number:
            assert number not in inventory
            inventory.append(number)
            number = world[number]["sibling"]
        queries = {
            "score": score,
            "moves": moves,
            "player": PLAYER,
            "location": parent,
            "inventory": inventory,
            "world_count": len(world),
            "world_sha256": digest(world),
            "player_sha256": digest(player),
            "location_sha256": digest(world[parent]) if parent else digest(None),
            "inventory_sha256": digest([world[n] for n in inventory]),
            "game_over": loss,
            "victory": victory,
        }
        # Outcome expectations come from measured response markers, not Fernz's
        # profile implementation or the reference's unsupported outcome getters.
        state = replace(self.bridge.from_jericho(native), game_over=loss, victory=victory)
        result = {
            "action": action,
            "state": state_fingerprint(state),
            "queries": queries,
            "reward": score - self.previous_score if action is not None else 0,
        }
        self.previous_score = score
        return result

    def case(self, name, actions, *, checkpoint=None, checkpoints=None):
        self.texts = []
        records = []
        for turn, action in enumerate(actions):
            records.append(self.capture(action))
            if checkpoints is not None and turn in CHECKPOINTS:
                checkpoints[turn] = self.env.get_state()
        # A final buffered word is absent from get_state(). Flush through a
        # public input, keeping ONLY the prefix before the next status display.
        # The flush's gameplay effects are discarded before the next case.
        names = tuple(obj["name"] for obj in self.world())
        flushed = self.env.step("")[0]
        marker = status_display(names).search(flushed)
        assert marker is not None, (name, "Missing reference status display")
        pending = flushed[: marker.start()].removesuffix(">").removesuffix(" ")
        text = "".join(self.texts) + pending
        return {
            "id": name,
            "seed": self.seed,
            "checkpoint": checkpoint,
            "steps": records,
            "text_sha256": digest(text.encode()),
        }

    def close(self):
        self.env.close()


def generate_lgop(path, *, smoke=False):
    recorder = Recorder(path)
    try:
        actions = walkthrough()
        assert len(actions) == 389
        # Capture checkpoints during the single continuous winning playthrough.
        checkpoints = {}
        route = recorder.case(
            "winning-route",
            [None, *actions[: 4 if smoke else len(actions)]],
            checkpoints=checkpoints,
        )
        opening = {
            **route,
            "id": "opening",
            "steps": route["steps"][:5],
            "text_sha256": digest("".join(recorder.texts[:5]).encode()),
        }
        documents = {"walkthrough.json": {"cases": [route]}, "smoke.json": {"cases": [opening]}}
        if not smoke:
            last = route["steps"][-1]["queries"]
            assert last["victory"] and not last["game_over"]
            assert (last["score"], last["moves"]) == (326, 393)
            cases = []
            for checkpoint in CHECKPOINTS:
                for index, command in enumerate(COMMANDS):
                    recorder.restore(checkpoints[checkpoint])
                    cases.append(
                        recorder.case(
                            f"{checkpoint}:{index}",
                            (command, "look", "inventory"),
                            checkpoint=checkpoint,
                        )
                    )
            documents["detours.json"] = {"cases": cases}
            cases = []
            for checkpoint in (100, 190, 350):
                recorder.restore(checkpoints[checkpoint])
                cases.append(
                    recorder.case(
                        f"save-restore:{checkpoint}",
                        ("save", "wait", "restore", "look", "inventory"),
                        checkpoint=checkpoint,
                    )
                )
            recorder.restore(checkpoints[100])
            cases.append(
                recorder.case(
                    "restart",
                    ("restart", "no", "look", "restart", "yes", "", "ne", "look", "inventory"),
                    checkpoint=100,
                )
            )
            documents["lifecycle.json"] = {"cases": cases}
    finally:
        recorder.close()
    if not smoke:
        cases = []
        for name, seed, actions in partial_routes():
            recorder = Recorder(path, seed)
            try:
                cases.append(recorder.case(name, (None, *actions)))
            finally:
                recorder.close()
        assert any(row["queries"]["game_over"] for case in cases for row in case["steps"])
        documents["partials.json"] = {"cases": cases}
    documents["manifest.json"] = {
        "format_version": FORMAT_VERSION,
        "kind": "lgop-gameplay",
        "story": STORY,
        "seed": SEED,
        "checkpoints": list(CHECKPOINTS),
        "reference": {
            "name": "Jericho",
            "version": REFERENCE_VERSION,
            "interface": "public Python execution and snapshots; specification-derived queries",
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
