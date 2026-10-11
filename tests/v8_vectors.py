"""V8 behavior fingerprints shared by portable and live comparisons."""

from .observation_helpers import join_observations
from .v5_corpus_vectors import object_fingerprint, object_layout
from .v8_cases import BOOT_ACTIONS, SEED, story_identity
from .vector_archive import digest


def text_content(observation, game, *, opening=False, after_character=False, fernz=False):
    """Project measured prompt clipping, preserving both windows and punctuation."""
    text = observation.text if fernz else observation
    if fernz:
        if opening or after_character:
            text = text[1:]  # Public reset/character responses clip their first character.
        # Snack Time prints a literal > in its opening sound description.
        end = text.find("\n>") + 1 if game == "snacktime" else text.find(">")
        if end > 0 and not text.lstrip().startswith(">"):
            # When only a prompt/status is emitted (e.g. cancelling restart),
            # the public reference retains it rather than clipping the suffix.
            text = text[: max(0, end - 2)]
    text = " ".join(text.replace("\r\n", "\n").split())
    return "" if text == ">" else text


def reset_fernz(env, game):
    observation = env.reset()[0]
    for action in BOOT_ACTIONS.get(game, ()):
        assert env.get_state().input_request.character == (action != "no")
        observation = join_observations(observation, env.step(action)[0])
    return observation


def capture(env, original, game, action, observation):
    snapshot = env.get_state()
    ram = snapshot[0].tobytes()
    a, period, counter = snapshot[7]
    assert int(snapshot[6]) in (0xE4, 0xF6)
    return {
        "action": action,
        "text_sha256": digest(text_content(observation, game).encode()),
        "objects": object_fingerprint(ram, object_layout(original)),
        "globals_sha256": globals_digest(ram),
        "input_address": int(snapshot[2]) - 1,
        "character_input": int(snapshot[6]) == 0xF6,
        "rng": [int(a) & 0x7FFFFFFF, int(period), int(counter) if period else 0],
    }


def globals_digest(ram):
    base = int.from_bytes(ram[12:14], "big")
    return digest(ram[base : base + 480])


def assert_record(env, game, record, observation, *, check_text=True):
    state = env.get_state()
    assert not env.done
    assert state.input_request.character == record["character_input"]
    assert state.input_request.instruction_address == record["input_address"]
    assert [state.rng.state, state.rng.period, state.rng.position] == record["rng"]
    assert object_fingerprint(state.ram, object_layout(env.story.data)) == record["objects"]
    assert globals_digest(state.ram) == record["globals_sha256"]
    if check_text:
        text = text_content(observation, game, opening=record["action"] is None, fernz=True)
        assert digest(text.encode()) == record["text_sha256"], (game, record["action"], text)


def replay_opening(path, game, documents):
    from fernz import FernzEnv

    header = documents["manifest.json"]
    assert header["story"] == story_identity(game)
    assert digest(path.read_bytes()) == header["story"]["file_sha256"]
    env = FernzEnv(path, seed=SEED, **header["geometry"])
    try:
        record = documents["opening.json"]["cases"][0]["steps"][0]
        assert_record(env, game, record, reset_fernz(env, game))
    finally:
        env.close()


def replay_actions(path, game, documents):
    from fernz import FernzEnv

    from .test_save_restore import Storage

    header = documents["manifest.json"]
    assert digest(path.read_bytes()) == header["story"]["file_sha256"]
    storage = Storage()
    env = FernzEnv(
        path,
        seed=SEED,
        **header["geometry"],
        save_handler=storage.save,
        restore_handler=storage.restore,
    )
    try:
        for case in documents["actions.json"]["cases"]:
            first, *records = case["steps"]
            assert_record(env, game, first, reset_fernz(env, game))
            for turn, record in enumerate(records):
                before = env.get_state()
                observation = env.step(record["action"], max_steps=2_000_000)[0]
                try:
                    assert_record(env, game, record, observation)
                except AssertionError as error:
                    error.add_note(f"{game}: {case['id']}, turn {turn}, {record['action']!r}")
                    raise
                if case["id"] != "persistence" and turn in (0, len(records) // 2, len(records) - 1):
                    after = env.get_state()
                    fork = env.copy()
                    try:
                        fork.set_state(before)
                        assert fork.step(record["action"], max_steps=2_000_000)[0] == observation
                        assert fork.get_state() == after and env.get_state() == after
                    finally:
                        fork.close()
            if case["id"] == "persistence":
                assert storage.data.startswith(b"FORM")
    finally:
        env.close()
