"""Shared assertions for live public-API comparisons and portable V3 replay."""

import re
from dataclasses import asdict
from functools import lru_cache

from .observation_helpers import plain_text
from .v3_cases import BOOT_ACTIONS
from .vector_archive import digest, state_fingerprint


# Exact geometry of the pinned reference's status display. Keep surrounding
# newlines and story text, including text adjacent to repeated clock updates.
@lru_cache(maxsize=128)
def status_display(names):
    rooms = "|".join(re.escape(name) for name in sorted(set(names), key=len, reverse=True) if name)
    return re.compile(
        rf" (?:{rooms}) {{40,}}(?:Score: -?\d+ {{10,}}Moves: \d+ {{14}}|Time: +\d+:\d+ [ap]m {{20}})"
    )


def reference_text(text, names):
    return status_display(tuple(names)).sub("", text.replace("\r\n", "\n"))


def fernz_text(text, *, opening, halted, game):
    text = plain_text(text).replace("\r\n", "\n")
    if opening:
        # The public reference removes the first startup line. It can be a
        # title, copyright notice, or introductory paragraph, depending on ROM.
        assert "\n" in text
        text = text.split("\n", 1)[1]
    else:
        assert text.startswith("\n")
        text = text[1:]
    if halted:
        return text + "\n"
    text = text.removesuffix(">").removesuffix(" ")
    if game == "cutthroat" and text.endswith("(YES or NO?)"):
        # Measured reference truncation of this specific waiting prompt.
        text = text.removesuffix(" NO?)")
    return text


def reset_fernz(env, game):
    observation, info = env.reset()
    observation = observation.text
    for action in BOOT_ACTIONS.get(game, ()):
        text, _, _, info = env.step(action)
        observation += text.text
    return observation, 0, False, info


def query_fingerprint(env, game=None):
    world = env.get_world_objects(clean=False)
    records = [asdict(obj) for obj in world]
    location = env.get_player_location()
    location_number = location.num if location else 0
    if game == "cutthroat" and env.done and env.victory():
        # The native winning snapshot includes post-quit world changes. A
        # standalone executable probe at the story's quit (0x1115b) confirms
        # the left-hand values; retain exact assertions for every difference.
        changes = {
            1: {"child": (0, 184)},
            18: {"child": (0, 28)},
            28: {"parent": (222, 18), "sibling": (105, 0)},
            90: {"sibling": (184, 0)},
            184: {"parent": (56, 1)},
            222: {"child": (28, 105)},
        }
        for number, fields in changes.items():
            for field, (actual, reference) in fields.items():
                assert records[number][field] == actual
                records[number][field] = reference
        assert records[1]["attr"][29] == 0
        records[1]["attr"][29] = 1
        assert location_number == 56
        location_number = 1
    return {
        "world_count": len(world),
        "world_sha256": digest(records),
        "inventory_sha256": digest([records[obj.num] for obj in env.get_inventory()]),
        "player_sha256": digest(records[env.get_player_object().num]),
        "location_sha256": digest(records[location_number]) if location_number else digest(None),
        "location": location_number,
        "player": env.get_player_object().num,
        "score": env.get_score(),
        "moves": env.get_moves(),
        "max_score": env.get_max_score(),
        "game_over": env.game_over(),
        "victory": env.victory(),
    }


def assert_record(env, response, record, game):
    observation, reward, done, info = response
    text = fernz_text(
        observation, opening=record["action"] is None, halted=record["halted"], game=game
    )
    assert digest(text.encode()) == record["observation_sha256"], (
        game,
        record["action"],
        text,
        record["observation_sha256"],
    )
    assert type(reward) is int and reward == record["reward"]
    assert type(done) is bool and done is record["halted"]
    assert env.done is done
    expected_info = dict(record["info"])
    expected_queries = dict(record["queries"])
    if record["halted"]:
        # Like Zork I, these measured terminal paths report one extra native
        # move after quit. Fernz stops with the actual story counter.
        expected_info["moves"] -= 1
        expected_queries["moves"] -= 1
    assert info == expected_info
    before = env.get_state()
    assert query_fingerprint(env, game) == expected_queries
    assert record["done"] is (expected_queries["game_over"] or expected_queries["victory"])
    assert env.get_state() == before, "Read-only queries changed interpreter state"
    if not record["halted"]:
        assert state_fingerprint(before) == record["state"]
    else:
        assert record["state"] is None


def step_and_check(env, record, game):
    try:
        result = reset_fernz(env, game) if record["action"] is None else env.step(record["action"])
        assert_record(env, result, record, game)
        return result
    except (AssertionError, RuntimeError, ValueError) as error:
        error.add_note(
            f"{game}: {record['action']!r}; expected room {record['queries']['location']}"
        )
        raise
