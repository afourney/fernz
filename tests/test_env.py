from pathlib import Path

import pytest

from fernz import FernzEnv, StoryFormatError

from .story_files import story_bytes


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


def test_execution_is_explicitly_unimplemented(tmp_path):
    game = tmp_path / "game.z3"
    game.write_bytes(story_bytes())
    env = FernzEnv(game)
    with pytest.raises(NotImplementedError, match="story execution is not implemented"):
        env.reset()
    with pytest.raises(NotImplementedError, match="story execution is not implemented"):
        env.step("look")
    env.close()
    assert game.read_bytes() == story_bytes()
