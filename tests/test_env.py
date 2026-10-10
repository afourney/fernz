from pathlib import Path

import pytest

from fernz import ExecutionError, FernzEnv, StoryFormatError

from .story_files import READ, program_bytes, put_word, story_bytes


@pytest.mark.parametrize("as_string", [False, True])
def test_constructor_loads_story_without_executing_it(tmp_path, as_string):
    game = tmp_path / "story.data"
    game.write_bytes(story_bytes())
    env = FernzEnv(str(game) if as_string else game)
    assert env.game_path == game
    assert isinstance(env.game_path, Path)
    assert env.story.header.version == 3
    assert env.memory.story is env.story
    env.memory.write_byte(0x100, 42)
    other = FernzEnv(game)
    assert other.memory.read_byte(0x100) == 0
    other.close()
    env.close()
    env.close()
    assert game.read_bytes() == story_bytes()


def test_invalid_story_is_rejected(tmp_path):
    game = tmp_path / "invalid.z3"
    game.write_bytes(b"not a story")
    with pytest.raises(StoryFormatError, match="64-byte header"):
        FernzEnv(game)


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        FernzEnv(tmp_path / "missing.z3")


def test_directory_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="not a regular file"):
        FernzEnv(tmp_path)


@pytest.mark.parametrize("version", (1, 2, 4, 5, 6, 7, 8))
def test_execution_of_other_versions_is_explicitly_unimplemented(tmp_path, version):
    game = tmp_path / "game.z3"
    game.write_bytes(story_bytes(version))
    env = FernzEnv(game)
    with pytest.raises(NotImplementedError, match="supports V3 only"):
        env.reset()
    with pytest.raises(NotImplementedError, match="Command input"):
        env.step("look")
    env.close()
    assert game.read_bytes() == story_bytes(version)


def test_reset_runs_to_input_and_restores_memory_stack_and_output(tmp_path):
    game = tmp_path / "game.z3"
    # Increment score, push a value, print 'A', then wait for input.
    data = program_bytes(bytes.fromhex("95 11 e8 7f 2a e5 7f 41") + READ)
    game.write_bytes(data)
    env = FernzEnv(game, seed=0)
    assert env.reset() == ("A", {"score": 1, "moves": 0})
    memory = env.memory
    env.memory.write_word(env.story.header.globals_table + 2, 999)
    assert env.reset() == ("A", {"score": 1, "moves": 0})
    assert env.memory is memory
    assert env._machine.frames[0].stack == [42]
    assert game.read_bytes() == data


def test_time_game_does_not_mislabel_time_as_score_and_moves(tmp_path):
    data = bytearray(program_bytes(READ))
    data[1] |= 2
    put_word(data, 0x102, 23)
    put_word(data, 0x104, 59)
    game = tmp_path / "time.z3"
    game.write_bytes(data)
    assert FernzEnv(game).reset() == ("", {"hours": 23, "minutes": 59})


def test_reset_after_execution_failure(tmp_path):
    game = tmp_path / "loop.z3"
    game.write_bytes(program_bytes(bytes.fromhex("95 11 8c ff fd")))
    env = FernzEnv(game)
    for _ in range(2):
        with pytest.raises(ExecutionError, match="budget"):
            env.reset(max_steps=10)
        assert env.memory.read_word(0x102) == 5


def test_step_is_explicitly_deferred(tmp_path):
    game = tmp_path / "input.z3"
    game.write_bytes(program_bytes(READ))
    env = FernzEnv(game)
    env.reset()
    with pytest.raises(NotImplementedError, match="Command input"):
        env.step("look")
