"""V5 startup measurements and portable replay with explicit presentation rules."""

import re

from .v3_oracle import word
from .v5_corpus import BOOT_ACTIONS, SEED, WINDOWED_OPENINGS, story_identity
from .vector_archive import digest


def object_layout(data):
    """Infer the original contiguous entry extent, independently of Fernz."""
    base = word(data, 10) + 126
    cursor, limit, count = base, word(data, 14), 0
    while cursor < limit:
        table = word(data, cursor + 12)
        assert cursor + 14 <= table < word(data, 14)
        limit = min(limit, table)
        cursor += 14
        count += 1
        assert count <= 65535 and cursor <= limit
    return base, count


def object_fingerprint(ram, layout):
    """Hash all entries and each bounded name/property table, including duplicates."""
    base, count = layout
    tables = []
    for number in range(count):
        table = word(ram, base + 14 * number + 12)
        cursor = table + 1 + 2 * ram[table]
        while ram[cursor]:
            first = ram[cursor]
            if first & 128:
                size = ram[cursor + 1] & 63 or 64
                cursor += 2 + size
            else:
                cursor += 3 if first & 64 else 2
            assert cursor < len(ram)
        tables.append(digest(ram[table : cursor + 1]))
    return {
        "count": count,
        "entries_sha256": digest(ram[base : base + 14 * count]),
        "tables_sha256": digest(tables),
    }


def observation_text(text, game, *, opening=False, fernz=False):
    """Compare text content, with whitespace, prompt, and measured status handling."""
    text = text.replace("\r\n", "\n")
    if fernz and opening:
        # Measured V5 reset clipping: one character, not one line. Spirit
        # loses its title's first letter; ZTUU loses an opening quotation mark.
        text = text[1:]
    if fernz and game == "acorncourt":
        text, count = re.subn(r"\n\n\[[^\n]+\]> $", "", text)
        assert count == 1
        # The reference also strips this bracketed score notification with
        # the room prompt. Its state change remains covered by the hashes.
        text = text.removesuffix("\n\n[Your score has just gone up by ten points.]")
    if fernz and game == "enter" and text.endswith("nothing >> "):
        text = text.removesuffix("g >> ")
    if game == "sherlock" and not fernz:
        # Clock updates are upper-window output, sometimes adjoining narrative.
        text = re.sub(
            r"(?: {39}[^\n]*?| {1,4}-?\d+)?(?:Saturday|Sunday|Monday) +\d+:\d{2}:\d{2} [ap]\.m\.",
            "",
            text,
        )
    if game == "huntdark" and not fernz:
        text = text.removesuffix(" " * 128 + "Pain")
    text = text.strip().removeprefix(">").removesuffix(">").strip()
    if fernz and (game in ("murdac", "theatre") or (game == "karn" and opening)):
        # Measured final punctuation clipped along with the reference prompt.
        assert text[-1] in (".!" if game == "murdac" else "?")
        text = text[:-1]
    if fernz and game == "zenon" and text.endswith("!"):
        text = text[:-1]
    return " ".join(text.split())


def reset_fernz(env, game):
    observation = env.reset()[0]
    for action in BOOT_ACTIONS.get(game, ()):
        request = env.get_state().input_request
        assert request.character == (game != "jewel")
        continuation = env.step(action)[0]
        if game != "jewel":
            observation += continuation
    assert not env.get_state().input_request.character
    return observation


def capture(env, game, layout, action, observation):
    snapshot = env.get_state()
    ram = snapshot[0].tobytes()
    a, period, counter = snapshot[7]
    assert int(snapshot[6]) in (0xE4, 0xF6), "Expected a pending input instruction"
    return {
        "action": action,
        "observation_sha256": None
        if action is None and game in WINDOWED_OPENINGS
        else digest(observation_text(observation, game, opening=action is None).encode()),
        "objects": object_fingerprint(ram, layout),
        "input_address": int(snapshot[2]) - 1,
        "character_input": int(snapshot[6]) == 0xF6,
        "rng": [int(a) & 0x7FFFFFFF, int(period), int(counter) if period else 0],
    }


def assert_record(env, game, layout, record, observation):
    state = env.get_state()
    assert not env.done and state.input_request.character == record["character_input"]
    assert state.input_request.instruction_address == record["input_address"]
    assert [state.rng.state, state.rng.period, state.rng.position] == record["rng"]
    assert object_fingerprint(state.ram, layout) == record["objects"], (game, record["action"])
    if record["observation_sha256"] is not None:
        text = observation_text(observation, game, opening=record["action"] is None, fernz=True)
        assert digest(text.encode()) == record["observation_sha256"], (game, record["action"], text)
    else:
        assert record["action"] is None and game in WINDOWED_OPENINGS


def replay_startup(path, game, document):
    from fernz import FernzEnv

    assert digest(path.read_bytes()) == story_identity(game)["file_sha256"]
    layout = object_layout(path.read_bytes())
    env = FernzEnv(path, seed=SEED)
    try:
        for case in document["cases"]:
            assert case["seed"] == SEED
            first, *records = case["steps"]
            assert first["action"] is None
            assert_record(env, game, layout, first, reset_fernz(env, game))
            initial = env.get_state()
            for record in records:
                before = env.get_state()
                observation = env.step(record["action"])[0]
                assert_record(env, game, layout, record, observation)
                after = env.get_state()
                env.set_state(before)
                assert env.step(record["action"])[0] == observation
                assert env.get_state() == after
            fork = env.copy()
            try:
                assert fork.get_state() == env.get_state()
                assert_record(fork, game, layout, first, reset_fernz(fork, game))
                assert fork.get_state() == initial
                assert env.get_state() == after
            finally:
                fork.close()
    finally:
        env.close()
