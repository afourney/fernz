"""Record full V5 routes using public Jericho calls and independently decoded RAM."""

from ..v5_walkthrough_cases import GAMES
from ..v5_walkthrough_vectors import capture
from ..vector_archive import digest
from .v5_startup_vectors import manifest, startup_document


def counter_document(env, game):
    case = GAMES[game]
    env.reset()
    state = env.get_state()
    ram = state[0]
    base = int.from_bytes(ram[12:14].tobytes(), "big")
    records = []
    try:
        for field in ("score", "moves"):
            for value in (0, 1, 255, 256, 32767, 32768, 65535):
                changed = ram.copy()
                address = base + 2 * case[f"{field}_global"]
                changed[address : address + 2] = list(value.to_bytes(2, "big"))
                env.set_state((changed, *state[1:]))
                records.append(
                    {
                        "field": field,
                        "value": value,
                        "score": int(env.get_score()),
                        "moves": int(env.get_moves()),
                    }
                )
    finally:
        env.set_state(state)
    return {"cases": [{"id": "counter-widths", "seed": case["seed"], "steps": records}]}


def generate_walkthrough(path, game):
    from jericho import FrotzEnv

    case = GAMES[game]
    path = path.resolve()
    original = path.read_bytes()
    documents = {"breadth.json": startup_document(path, game)}
    env = FrotzEnv(str(path), seed=case["seed"])
    try:
        documents["counters.json"] = counter_document(env, game)
        observation, info = env.reset()
        ram = env.get_state()[0]
        geometry = {"screen_width": int(ram[0x21]), "screen_height": int(ram[0x20])}
        actions = env.get_walkthrough()
        assert len(actions) == case["length"]
        route, text = [], []
        for turn, action in enumerate([None, *actions]):
            if turn:
                # Pass a key at read_char so no unused command suffix remains
                # in the reference's external input queue.
                if int(env.get_state()[6]) == 0xF6:
                    action = action[:1]
                response = env.step(action)
            else:
                response = observation, 0, False, info
            record, content = capture(env, original, game, turn, action, response)
            text.append(content)
            if record["text_group_end"]:
                record["text_sha256"] = digest(" ".join(" ".join(text).split()).encode())
                text.clear()
            route.append(record)
        assert not text and route[-1]["queries"]["victory"]
        documents["walkthrough.json"] = {
            "cases": [{"id": "winning-route", "seed": case["seed"], "steps": route}]
        }
    finally:
        env.close()
    header = manifest(game, documents)
    header.update(kind="v5-walkthrough", record_version=1, seed=case["seed"])
    header["geometry"] = geometry
    documents["manifest.json"] = header
    return documents
