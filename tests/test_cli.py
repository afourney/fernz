import subprocess
import sys

import pytest

from fernz import _cli


def test_help(capsys):
    with pytest.raises(SystemExit) as exc:
        _cli.main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "game" in captured.out
    assert "not implemented" in captured.out
    assert captured.err == ""


@pytest.mark.parametrize("args", [[], ["--unknown"]])
def test_invalid_arguments(args, capsys):
    with pytest.raises(SystemExit) as exc:
        _cli.main(args)
    assert exc.value.code == 2
    assert "usage:" in capsys.readouterr().err


@pytest.mark.parametrize("directory", [False, True])
def test_invalid_path(tmp_path, capsys, directory):
    path = tmp_path if directory else tmp_path / "missing.z3"
    assert _cli.main([str(path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "fernz:" in captured.err
    assert str(path) in captured.err
    assert "Traceback" not in captured.err


def test_existing_game_reports_unimplemented(tmp_path, capsys):
    game = tmp_path / "game with spaces.z3"
    game.write_bytes(b"synthetic test input")
    assert _cli.main([str(game)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "story execution is not implemented" in captured.err
    assert "Traceback" not in captured.err
    assert game.read_bytes() == b"synthetic test input"


def test_cli_delegates_to_library_and_closes(tmp_path, monkeypatch, capsys):
    calls = []

    class StubEnv:
        def __init__(self, path):
            calls.append(("init", path))

        def reset(self):
            calls.append("reset")
            raise NotImplementedError("test execution unavailable")

        def close(self):
            calls.append("close")

    monkeypatch.setattr(_cli, "FernzEnv", StubEnv)
    game = tmp_path / "game.z3"
    assert _cli.main([str(game)]) == 1
    assert calls == [("init", game), "reset", "close"]
    assert "test execution unavailable" in capsys.readouterr().err


def test_module_entry_point():
    result = subprocess.run(
        [sys.executable, "-m", "fernz", "--help"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0
    assert "usage: fernz" in result.stdout
    assert result.stderr == ""
