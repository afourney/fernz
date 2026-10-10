from pathlib import Path

import pytest

from fernz import FernzEnv


@pytest.mark.parametrize("as_string", [False, True])
def test_constructor_accepts_file_without_interpreting_it(tmp_path, as_string):
    game = tmp_path / "story.data"
    game.write_bytes(b"not a story")
    env = FernzEnv(str(game) if as_string else game)
    assert env.game_path == game
    assert isinstance(env.game_path, Path)
    env.close()
    env.close()
    assert game.read_bytes() == b"not a story"


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        FernzEnv(tmp_path / "missing.z3")


def test_directory_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="not a regular file"):
        FernzEnv(tmp_path)


def test_execution_is_explicitly_unimplemented(tmp_path):
    game = tmp_path / "empty.z3"
    game.touch()
    env = FernzEnv(game)
    with pytest.raises(NotImplementedError, match="story execution is not implemented"):
        env.reset()
    with pytest.raises(NotImplementedError, match="story execution is not implemented"):
        env.step("look")
    env.close()
    assert game.read_bytes() == b""
