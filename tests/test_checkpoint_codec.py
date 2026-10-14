"""Public checkpoint persistence using synthetic stories, never pickle."""

import base64
import json
from dataclasses import replace
from pathlib import Path

import pytest

from fernz import FernzEnv, GameState, Story

from .save_story import save_story
from .story_files import READ, program_bytes

CHAR = bytes.fromhex("f6 7f 01 10")
DRAW = bytes.fromhex("e7 3f 7f ff 11 e6 bf 11")


def read(version, character=False):
    return CHAR if character else READ + (b"\x10" if version >= 5 else b"")


def environment(version=5, *, character=False, seed=42, prefix=b""):
    request = read(version, character)
    story = Story(program_bytes(prefix + request + DRAW + request + b"\xba", version=version))
    env = FernzEnv(story, seed=seed)
    env.reset()
    return env


@pytest.mark.parametrize(
    "version,character",
    [(3, False), (4, False), (4, True), (5, False), (5, True), (8, False), (8, True)],
)
def test_public_roundtrip_continues_through_input_and_quit(version, character):
    env = environment(version, character=character)
    action = " " if character else "look"
    for _ in range(3):
        state = env.get_state()
        payload = state.to_bytes()
        restored = GameState.from_bytes(payload, story=env.story)
        assert restored == state
        assert restored.to_bytes() == payload
        assert env.get_state() == state
        candidate = FernzEnv(env.story, seed=99)
        candidate.set_state(restored)
        assert candidate.get_state() == state
        if env.done:
            assert candidate.done and not candidate.awaiting_character
            break
        assert candidate.awaiting_character == character
        assert candidate.step(action) == env.step(action)
        assert candidate.get_state() == env.get_state()
    assert env.done


@pytest.mark.parametrize("version", (3, 4, 5, 8))
@pytest.mark.parametrize("host_seed", (None, 0, 42))
@pytest.mark.parametrize("opcode_seed", (None, -5, -1000))
def test_rng_roundtrip_replays_every_generator_without_entropy(
    monkeypatch, version, host_seed, opcode_seed
):
    from fernz import _random

    prefix = (
        b""
        if opcode_seed is None
        else bytes.fromhex("e7 3f") + (opcode_seed & 0xFFFF).to_bytes(2, "big") + b"\x10"
    )
    env = environment(version, seed=host_seed, prefix=prefix)
    before = env.get_state()

    def unexpected(*args, **kwargs):
        pytest.fail("Serialization and restore must not seed from entropy")

    monkeypatch.setattr(_random.secrets, "randbits", unexpected)
    candidate = FernzEnv(env.story)
    candidate.set_state(GameState.from_bytes(before.to_bytes(), story=env.story))
    assert candidate.get_state() == before
    assert env.step("look") == candidate.step("look")
    assert env.get_state() == candidate.get_state()


@pytest.mark.parametrize("high", (False, True))
def test_nested_frames_and_high_addresses_survive_encoding(high):
    env = FernzEnv(Story(save_story(high=high)), seed=12, save_handler=lambda data: True)
    env.reset()
    env.step("save")
    state = env.get_state()
    assert len(state.frames) == 3
    # The inner routine already printed (and popped) its stack sentinel.
    assert [frame.stack for frame in state.frames] == [(0x1111,), (0x2222,), ()]
    assert (state.pc > 0xFFFF) == high
    other = FernzEnv(env.story)
    other.set_state(GameState.from_bytes(state.to_bytes(), story=env.story))
    assert other.get_state() == state
    assert other.step("continue") == env.step("continue")
    assert other.get_state() == env.get_state()


def test_full_display_outcome_and_memory_stream_state_is_preserved():
    env = environment()
    state = env.get_state()
    state = replace(
        state,
        screen_enabled=False,
        game_over=True,
        victory=True,
        output=replace(
            state.output,
            window=1,
            split_lines=3,
            cursors=((5, 7), (2, 3)),
            fonts=(4, 1),
            styles=(3, 2),
            colours=(("#12abcd", "black"), ("red", "white")),
            buffered=False,
            memory_streams=((0x220, 2), (0x230, 3)),
        ),
    )
    restored = GameState.from_bytes(state.to_bytes(), story=env.story)
    assert restored == state
    env.set_state(state)
    other = FernzEnv(env.story)
    other.set_state(restored)
    assert env.step("look") == other.step("look")
    assert env.get_state() == other.get_state()
    assert env.get_state().output.memory_streams[-1][1] > 3


def test_receiving_environment_keeps_its_own_save_restore_handlers():
    calls = []
    stored = []

    def save(data):
        calls.append("save")
        stored.append(data)
        return True

    def restore():
        calls.append("restore")
        return stored[-1]

    def unexpected(*args, **kwargs):
        pytest.fail("The source environment's callbacks must not transfer")

    story = Story(
        program_bytes(READ + bytes.fromhex("b5 c2") + READ + bytes.fromhex("b6 c2") + READ)
    )
    source = FernzEnv(story, seed=12, save_handler=unexpected, restore_handler=unexpected)
    source.reset()
    before = source.get_state()
    target = FernzEnv(story, save_handler=save, restore_handler=restore)
    target.set_state(GameState.from_bytes(before.to_bytes(), story=story))
    target.step("save")
    target.step("restore")
    assert calls == ["save", "restore"]
    assert source.get_state() == before


@pytest.mark.parametrize("buffer_type", (bytes, bytearray, memoryview))
def test_decoding_accepts_byte_buffers(buffer_type):
    env = environment()
    state = env.get_state()
    assert GameState.from_bytes(buffer_type(state.to_bytes()), story=env.story) == state


@pytest.mark.parametrize("payload", (None, "{}", 123, [1, 2, 3]))
def test_wrong_argument_types_are_explicit(payload):
    env = environment()
    with pytest.raises(TypeError, match="bytes-like"):
        GameState.from_bytes(payload, story=env.story)
    with pytest.raises(TypeError, match="Story"):
        GameState.from_bytes(env.get_state().to_bytes(), story=None)


def test_wrong_story_is_rejected_and_live_environment_stays_unchanged():
    env = environment()
    state = env.get_state()
    different = Story(env.story.data[:-1] + b"\x01")
    other = FernzEnv(different, seed=99)
    other.reset()
    before = other.get_state()
    with pytest.raises(ValueError, match="different story"):
        GameState.from_bytes(state.to_bytes(), story=different)
    with pytest.raises(ValueError, match="different story"):
        other.set_state(GameState.from_bytes(state.to_bytes(), story=env.story))
    assert other.get_state() == before
    # Physical file padding is outside the story identity.
    assert GameState.from_bytes(state.to_bytes(), story=Story(env.story.data + b"padding")) == state


@pytest.mark.parametrize("version", (None, 0, 4, 6, True, 5.0, "5"))
def test_only_current_format_version_is_accepted(version):
    env = environment()
    document = json.loads(env.get_state().to_bytes())
    document["format_version"] = version
    with pytest.raises(ValueError, match="Unsupported checkpoint format version"):
        GameState.from_bytes(json.dumps(document).encode(), story=env.story)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"{",
        b"[]",
        b"null",
        b"\xff",
        b"{} trailing",
        b'{"format":"fernz-checkpoint","format":"fernz-checkpoint"}',
        b'{"value":{"pc":1,"pc":2}}',
        b'{"pc":NaN}',
        b'{"pc":Infinity}',
        b"[" * 2000 + b"]" * 2000,
    ],
)
def test_invalid_json_has_a_consistent_error(payload):
    env = environment()
    before = env.get_state()
    with pytest.raises(ValueError, match="Invalid Fernz checkpoint"):
        GameState.from_bytes(payload, story=env.story)
    assert env.get_state() == before


@pytest.mark.parametrize(
    "path,value",
    [
        (("format",), "Quetzal"),
        (("extra",), 0),
        (("story_sha256",), "0" * 64),
        (("ram",), "!"),
        (("ram",), ""),
        (("ram",), []),
        (("pc",), -1),
        (("pc",), 4097),
        (("pc",), True),
        (("pc",), 1.0),
        (("frames",), []),
        (("frames",), {}),
        (("frames", 0, "locals"), [1]),
        (("frames", 0, "stack"), [65536]),
        (("frames", 0, "store"), 0),
        (("frames", 0, "extra"), 0),
        (("rng", "host_seed"), -1),
        (("rng", "period"), 1000),
        (("rng", "position"), 1),
        (("rng", "python_state"), [3, [0], None]),
        (("screen_enabled",), 1),
        (("game_over",), "false"),
        (("halted",), True),
        (("input_request",), None),
        (("input_request", "text"), -1),
        (("input_request", "store"), 256),
        (("input_request", "character"), "false"),
        (("output", "width"), 0),
        (("output", "cursors"), [[1, 1], [1, 999]]),
        (("output", "fonts"), [1, 2]),
        (("output", "colours"), [["invalid", "black"], ["red", "white"]]),
        (("output", "memory_streams"), [[65535, 1]]),
        (("output", "buffered"), 1),
    ],
)
def test_invalid_payload_fields_are_rejected_without_mutation(path, value):
    env = environment()
    before = env.get_state()
    document = json.loads(before.to_bytes())
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError, match="Invalid Fernz checkpoint"):
        GameState.from_bytes(json.dumps(document).encode(), story=env.story)
    assert env.get_state() == before


def test_missing_fields_and_protected_header_bytes_are_rejected():
    env = environment()
    state = env.get_state()
    document = json.loads(state.to_bytes())
    del document["frames"][0]["locals"]
    with pytest.raises(ValueError, match="FrameState"):
        GameState.from_bytes(json.dumps(document).encode(), story=env.story)
    document = json.loads(state.to_bytes())
    ram = bytearray(state.ram)
    ram[0x0E] ^= 1
    document["ram"] = base64.b64encode(ram).decode()
    with pytest.raises(ValueError, match="protected header"):
        GameState.from_bytes(json.dumps(document).encode(), story=env.story)
    assert env.get_state() == state


@pytest.mark.parametrize(
    "field,value",
    [(0, 2), (1, []), (1, [0] * 624), (1, [0] * 624 + [625]), (2, 0.5)],
)
def test_malformed_python_rng_state_is_rejected(field, value):
    env = environment(seed=None)
    document = json.loads(env.get_state().to_bytes())
    document["rng"]["python_state"][field] = value
    with pytest.raises(ValueError, match="Invalid Fernz checkpoint"):
        GameState.from_bytes(json.dumps(document).encode(), story=env.story)


def test_truncated_payloads_are_rejected():
    env = environment()
    payload = env.get_state().to_bytes()
    for length in (0, 1, 20, len(payload) // 2, len(payload) - 1):
        with pytest.raises(ValueError, match="Invalid Fernz checkpoint"):
            GameState.from_bytes(payload[:length], story=env.story)


@pytest.mark.parametrize(
    "filename,expected",
    [("checkpoint_schema5.json", "14545"), ("checkpoint_schema5_python_rng.json", "13652")],
)
def test_portable_fixture_continues_on_each_supported_python_and_platform(filename, expected):
    # Independent synthetic V5 story, explicit host seed: no game ROM content.
    # The committed JSON pins the current public format across Python versions.
    env = environment()
    payload = (Path(__file__).parent / "vectors" / filename).read_bytes()
    state = GameState.from_bytes(payload, story=env.story)
    assert replace(state, rng=env.get_state().rng) == env.get_state()
    assert payload == state.to_bytes()
    env.set_state(state)
    assert env.step("look")[0].text == "\n" + expected
