"""Story metadata, detached locations, and checkpointed response outcomes."""

from dataclasses import replace
from hashlib import sha256

import pytest

from fernz import ExecutionError, FernzEnv, ZObject, _profiles
from fernz._profiles import StoryProfile

from .observation_helpers import window_text
from .story_files import READ, program_bytes, zchars


def printed(text):
    return b"".join(b"\xe5\x7f" + bytes((13 if c == "\n" else ord(c),)) for c in text)


@pytest.fixture
def profiled_story(tmp_path, monkeypatch):
    # Independent story and profile: no game ROM or reference installation.
    # Lose at startup, take an ordinary turn, then win and halt.
    data = program_bytes(
        printed("lost\n") + READ + printed("ordinary\n") + READ + printed("won\n") + b"\xba",
        (0x100, b"\x00\x01"),
        (0x85, b"\x02\x00"),
        (0x200, b"\x01" + zchars(6, 7, 8)),
    )
    path = tmp_path / "profile.z3"
    path.write_bytes(data)
    monkeypatch.setitem(
        _profiles._PROFILES,
        sha256(data).hexdigest(),
        StoryProfile(77, frozenset({"lost"}), frozenset({"won"})),
    )
    return path


def outcomes(env):
    return env.game_over(), env.victory()


def location(env):
    room = env.get_player_location()
    assert isinstance(room, ZObject)
    return room.num, room.name


def test_queries_are_detached_and_do_not_execute_or_change_rng(profiled_story, capsys):
    env = FernzEnv(profiled_story, seed=42)
    assert env.get_max_score() == 77  # Metadata is available before reset.
    for query in (env.get_player_location, env.game_over, env.victory):
        with pytest.raises(RuntimeError, match="reset"):
            query()
    observation, _ = env.reset()
    assert observation.text == window_text(observation) == "lost\n"
    saved = env.get_state()
    for _ in range(2):
        room = env.get_player_location()
        assert isinstance(room, ZObject)
        assert (room.num, room.name) == (1, "abc")
        assert outcomes(env) == (True, False)
        assert env.get_max_score() == 77
        assert env.get_state() == saved
    assert capsys.readouterr() == ("", "")
    room.name = "edited"
    assert location(env) == (1, "abc")
    env.memory.write_bytes(0x201, zchars(29, 30, 31))
    assert location(env) == (1, "xyz")
    assert (room.num, room.name) == (1, "edited")
    observation = env.step("look")[0]
    assert observation.text == window_text(observation) == "\nordinary\n"


def test_outcomes_copy_restore_reset_and_failed_input(profiled_story, monkeypatch):
    env = FernzEnv(profiled_story, seed=42)
    env.reset()
    lost = env.get_state()
    assert lost.format_version == 5 and lost.game_over and not lost.victory
    assert not env.done  # A reported loss is independent of VM quit.
    other = env.copy()
    with pytest.raises(ValueError):
        other.step("two\nlines")
    assert other.get_state() == lost
    other.step("look")
    assert outcomes(other) == (False, False)
    assert outcomes(env) == (True, False)
    other.step("finish")
    won = other.get_state()
    assert other.done and outcomes(other) == (False, True)
    assert outcomes(other.copy()) == (False, True)
    fresh = FernzEnv(profiled_story)

    def forbidden(bits):
        pytest.fail("Restoring must not draw entropy")

    monkeypatch.setattr("fernz._random.secrets.randbits", forbidden)
    for candidate in (env, other, fresh):
        candidate.set_state(won)
        assert candidate.get_state() == won
        assert candidate.done and outcomes(candidate) == (False, True)
        candidate.set_state(lost)
        assert not candidate.done and outcomes(candidate) == (True, False)
        candidate.reset()
        assert candidate.get_state() == lost


def test_failure_requires_recovery_and_invalid_outcomes_restore_atomically(profiled_story):
    env = FernzEnv(profiled_story, seed=42)
    env.reset()
    before = env.get_state()
    for field in ("game_over", "victory"):
        with pytest.raises(TypeError, match="outcome"):
            env.set_state(replace(before, **{field: 1}))
        assert env.get_state() == before
    with pytest.raises(ExecutionError, match="budget"):
        env.step("look", max_steps=1)
    assert env.get_max_score() == 77
    for query in (env.game_over, env.victory, env.get_player_location):
        with pytest.raises(RuntimeError, match="reset"):
            query()
    env.set_state(before)
    assert outcomes(env) == (True, False)


def test_profile_identifies_addressable_bytes_not_filename_or_header(profiled_story, tmp_path):
    padded = tmp_path / "renamed.z8"
    padded.write_bytes(profiled_story.read_bytes() + b"padding")
    assert FernzEnv(padded).get_max_score() == 77
    changed = bytearray(profiled_story.read_bytes())
    changed[-1] ^= 1  # Retain release, serial, checksum, and original filename.
    profiled_story.write_bytes(changed)
    env = FernzEnv(profiled_story)
    env.reset()
    for query in (env.get_max_score, env.game_over, env.victory):
        with pytest.raises(NotImplementedError, match="story profile"):
            query()
    assert location(env) == (1, "abc")


def test_known_player_location_is_its_immediate_container(profiled_story, monkeypatch):
    digest = sha256(profiled_story.read_bytes()).hexdigest()
    monkeypatch.setitem(
        _profiles._PROFILES, digest, replace(_profiles._PROFILES[digest], player_object=2)
    )
    env = FernzEnv(profiled_story)
    env.reset()
    env.memory.write_word(0x100, 255)  # Status room differs from the container.
    env.memory.write_byte(0x87 + 4, 1)  # Player 2 is inside object 1.
    assert location(env) == (1, "abc")
    env.memory.write_byte(0x87 + 4, 0)
    assert env.get_player_location() is None


@pytest.mark.parametrize("time_game", [False, True])
def test_unprofiled_location_uses_v3_status_and_handles_absent_or_invalid_data(tmp_path, time_game):
    data = bytearray(program_bytes(READ + b"\xba", (0x85, b"\x02\x00")))
    data[1] |= 2 if time_game else 0
    path = tmp_path / "unknown.z3"
    path.write_bytes(data)
    env = FernzEnv(path)
    env.reset()
    assert env.get_player_location() is None
    env.memory.write_word(0x100, 1)
    assert location(env) == (1, "")
    env.memory.write_word(0x100, 256)
    before = env.get_state()
    with pytest.raises(ExecutionError, match="object number"):
        env.get_player_location()
    assert env.get_state() == before
    env.memory.write_word(0x100, 1)
    env.memory.write_word(0x85, 0x2FF)
    env.memory.write_byte(0x2FF, 1)
    with pytest.raises(ExecutionError, match="outside dynamic"):
        env.get_player_location()


def test_restart_and_quetzal_restore_classify_the_new_response(tmp_path, monkeypatch):
    from .test_save_restore import Storage

    # SAVE resumes just before 'ready'. READ, print 'lost', READ, RESTORE.
    data = program_bytes(
        b"\xb5\xc2" + printed("ready\n") + READ + printed("lost\n") + READ + b"\xb6\xc2\xba"
    )
    profile = StoryProfile(77, frozenset({"lost"}), frozenset({"won"}))
    monkeypatch.setitem(_profiles._PROFILES, sha256(data).hexdigest(), profile)
    path = tmp_path / "restore.z3"
    path.write_bytes(data)
    storage = Storage()
    env = FernzEnv(path, save_handler=storage.save, restore_handler=storage.restore)
    env.reset()
    assert outcomes(env) == (False, False)
    env.step("lose")
    assert outcomes(env) == (True, False)
    env.step("restore")
    assert outcomes(env) == (False, False)

    # Startup prints 'ready', a turn prints 'lost', then RESTART prints 'ready'.
    data = program_bytes(printed("ready\n") + READ + printed("lost\n") + READ + b"\xb7")
    monkeypatch.setitem(_profiles._PROFILES, sha256(data).hexdigest(), profile)
    path.write_bytes(data)
    env = FernzEnv(path)
    env.reset()
    env.step("lose")
    assert outcomes(env) == (True, False)
    env.step("restart")
    assert outcomes(env) == (False, False)


def test_profile_matches_complete_lines_with_flexible_whitespace():
    profile = StoryProfile(77, frozenset({"loss marker"}), frozenset({"win marker"}))
    assert profile.outcomes("\r\n  loss  marker \r\n") == (True, False)
    assert profile.outcomes("Someone said win marker.\n") == (False, False)
    assert profile.outcomes("win marker\n") == (False, True)
    assert profile.outcomes("ordinary\n") == (False, False)


@pytest.mark.parametrize(
    "byte,signed,value,expected",
    [
        (False, True, 0xFFFF, -1),
        (False, False, 0xFFFF, 65535),
        (True, True, 0xABFF, -1),
        (True, False, 0xABFF, 255),
    ],
)
def test_profiled_score_and_move_globals_override_status_clock(
    profiled_story, monkeypatch, byte, signed, value, expected
):
    data = bytearray(profiled_story.read_bytes())
    data[1] |= 2  # V3 status line is a clock, not score/moves.
    profiled_story.write_bytes(data)
    monkeypatch.setitem(
        _profiles._PROFILES,
        sha256(data).hexdigest(),
        StoryProfile(
            400,
            frozenset(),
            frozenset(),
            score_global=115,
            moves_global=225,
            score_byte=byte,
            score_signed=signed,
        ),
    )
    env = FernzEnv(profiled_story, seed=0)
    env.reset()
    globals_ = env.story.header.globals_table
    env.memory.write_word(globals_ + 2 * 115, value)
    env.memory.write_word(globals_ + 2 * 225, 0xFEDC)
    before = env.get_state()
    assert env.get_score() == expected
    assert env.get_moves() == 0xFEDC
    assert env.get_state() == before
    env.close()


def test_hashed_outcomes_match_complete_normalized_lines():
    fingerprint = sha256(b"test outcome").hexdigest()
    profile = StoryProfile(1, frozenset(), frozenset(), victory_hashes=frozenset({fingerprint}))
    assert profile.outcomes("test   outcome\n>") == (False, True)
    assert profile.outcomes("test outcome>") == (False, True)
    assert profile.outcomes("prefix test outcome") == (False, False)
    assert profile.outcomes("test outcome suffix") == (False, False)
    assert profile.outcomes("") == (False, False)


def test_profile_can_distinguish_winning_and_losing_restart_menus():
    profile = StoryProfile(
        7,
        frozenset({"restart menu"}),
        frozenset({"won"}),
        victory_overrides_loss=True,
    )
    assert profile.outcomes("won\nrestart menu\n>") == (False, True)
    assert profile.outcomes("lost\nrestart menu\n>") == (True, False)
    assert profile.outcomes("ordinary response") == (False, False)
    # The policy is per profile; existing bindings may deliberately report both.
    assert replace(profile, victory_overrides_loss=False).outcomes("won\nrestart menu") == (
        True,
        True,
    )


@pytest.mark.parametrize("value,expected", [(255, 255), (256, 0), (65535, 255)])
def test_byte_move_counter_does_not_leak_high_byte(profiled_story, monkeypatch, value, expected):
    monkeypatch.setitem(
        _profiles._PROFILES,
        sha256(profiled_story.read_bytes()).hexdigest(),
        StoryProfile(77, frozenset(), frozenset(), moves_byte=True),
    )
    env = FernzEnv(profiled_story, seed=0)
    env.reset()
    env.memory.write_word(env.story.header.globals_table + 4, value)
    before = env.get_state()
    assert env.get_moves() == expected
    assert env.get_state() == before
    env.close()


def test_profile_without_fixed_maximum_keeps_other_queries(profiled_story, monkeypatch):
    identity = sha256(profiled_story.read_bytes()).hexdigest()
    monkeypatch.setitem(
        _profiles._PROFILES, identity, replace(_profiles._PROFILES[identity], max_score=None)
    )
    env = FernzEnv(profiled_story, seed=42)
    with pytest.raises(NotImplementedError, match="no fixed maximum"):
        env.get_max_score()
    env.reset()
    before = env.get_state()
    assert outcomes(env) == (True, False)
    assert location(env) == (1, "abc")
    assert env.get_score() == 0 and env.get_moves() == 0
    with pytest.raises(NotImplementedError, match="no fixed maximum"):
        env.get_max_score()
    assert env.get_state() == before
    env.close()
