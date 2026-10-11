"""Record full V8 routes and counter probes through public Jericho calls."""

import json
from pathlib import Path

from ..v8_cases import ROUTES, SEED
from ..v8_vectors import text_content
from ..v8_walkthrough_vectors import capture_turn
from ..vector_archive import digest


def walkthrough_document(env, original, game):
    observation, info = env.reset()
    if game in ("anchor", "partyfoul"):
        # Public walkthroughs repaired by black-box play at the pinned seed.
        actions = json.loads((Path(__file__).parents[1] / "routes" / f"{game}.json").read_text())
    else:
        actions = env.get_walkthrough()
    assert len(actions) == ROUTES[game]["length"]
    records, text = [], []
    for turn, action in enumerate([None, *actions]):
        after_character = bool(turn and records[-1]["character_input"])
        if turn:
            if after_character:
                action = action[:1]
            response = env.step(action)
        else:
            response = observation, 0, False, info
        record = capture_turn(env, original, game, action, response)
        record["after_character"] = after_character
        record["text_group_end"] = not record["character_input"] or turn == len(actions)
        text.append(text_content(response[0], game))
        record["text_sha256"] = None
        if record["text_group_end"]:
            record["text_sha256"] = digest(" ".join(" ".join(text).split()).encode())
            text.clear()
        records.append(record)
    assert not text
    assert records[-1]["queries"]["victory"] and env.get_score() == ROUTES[game]["score"]
    return {"cases": [{"id": "winning-route", "seed": SEED, "steps": records}]}


def counter_document(env, game):
    env.reset()
    state = env.get_state()
    ram = state[0]
    base = int.from_bytes(ram[12:14].tobytes(), "big")
    records = []
    try:
        for field in ("score", "moves"):
            if f"{field}_global" not in ROUTES[game]:
                continue  # Party Foul scores the winning response, not a RAM counter.
            for value in (0, 1, 255, 256, 32767, 32768, 65535):
                changed = ram.copy()
                address = base + 2 * ROUTES[game][f"{field}_global"]
                changed[address : address + 2] = list(value.to_bytes(2, "big"))
                if game == "afflicted":
                    env.reset()  # Its cached score is outside the public snapshot.
                env.set_state((changed, *state[1:]))
                if game == "afflicted" and field == "score":
                    # A rejected verb refreshes it without spending a story turn.
                    env.step("flibbertigibbet")
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
    return {"cases": [{"id": "counter-widths", "seed": SEED, "steps": records}]}
