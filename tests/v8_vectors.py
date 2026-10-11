"""V8 behavior fingerprints shared by portable and live comparisons."""

from .observation_helpers import join_observations
from .v5_corpus_vectors import object_fingerprint, object_layout
from .v8_cases import BOOT_ACTIONS, SEED, story_identity
from .vector_archive import digest


def text_content(observation, game, *, opening=False, fernz=False):
    """Project measured prompt clipping, preserving both windows and punctuation."""
    text = observation.text if fernz else observation
    if fernz:
        if opening:
            text = text[1:]  # Public reset clips its first character.
        # Snack Time prints a literal > in its opening sound description.
        end = text.find("\n>") + 1 if game == "snacktime" else text.find(">")
        if end > 0:
            text = text[: max(0, end - 2)]
    return " ".join(text.replace("\r\n", "\n").split())


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
        "input_address": int(snapshot[2]) - 1,
        "character_input": int(snapshot[6]) == 0xF6,
        "rng": [int(a) & 0x7FFFFFFF, int(period), int(counter) if period else 0],
    }


def assert_record(env, game, record, observation):
    state = env.get_state()
    assert not env.done
    assert state.input_request.character == record["character_input"]
    assert state.input_request.instruction_address == record["input_address"]
    assert [state.rng.state, state.rng.period, state.rng.position] == record["rng"]
    assert object_fingerprint(state.ram, object_layout(env.story.data)) == record["objects"]
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
