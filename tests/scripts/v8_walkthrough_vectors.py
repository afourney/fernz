"""Record two full V8 routes and counter probes through public Jericho calls."""

from ..v8_cases import ROUTES, SEED
from ..v8_walkthrough_vectors import capture_turn


def walkthrough_document(env, original, game):
    observation, info = env.reset()
    actions = env.get_walkthrough()
    assert len(actions) == ROUTES[game]["length"]
    records = [capture_turn(env, original, game, None, (observation, 0, False, info))]
    for action in actions:
        if int(env.get_state()[6]) == 0xF6:
            action = action[:1]
        records.append(capture_turn(env, original, game, action, env.step(action)))
    assert env.victory() and env.get_score() == ROUTES[game]["score"]
    return {"cases": [{"id": "winning-route", "seed": SEED, "steps": records}]}


def counter_document(env, game):
    env.reset()
    state = env.get_state()
    ram = state[0]
    base = int.from_bytes(ram[12:14].tobytes(), "big")
    records = []
    try:
        for field in ("score", "moves"):
            for value in (0, 1, 255, 256, 32767, 32768, 65535):
                changed = ram.copy()
                address = base + 2 * ROUTES[game][f"{field}_global"]
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
    return {"cases": [{"id": "counter-widths", "seed": SEED, "steps": records}]}
