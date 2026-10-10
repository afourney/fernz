import io
import json
import subprocess
import sys

import pytest

from fernz import _cli

from .story_files import READ, program_bytes, story_bytes


def test_help(capsys):
    with pytest.raises(SystemExit) as exc:
        _cli.main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "game" in captured.out
    assert "play supported V3" in " ".join(captured.out.split())
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
    game.write_bytes(story_bytes(5))
    assert _cli.main([str(game)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "supports V3 only" in captured.err
    assert "Traceback" not in captured.err
    assert game.read_bytes() == story_bytes(5)


def test_cli_prints_the_complete_opening_and_exits_at_eof(tmp_path, capsys, monkeypatch):
    game = tmp_path / "opening.z3"
    game.write_bytes(program_bytes(bytes.fromhex("e5 7f 41 bb e5 7f 3e") + READ))
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert _cli.main([str(game)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "A\n>"
    assert captured.err == ""


def test_cli_reads_commands_until_story_quits(tmp_path, capsys, monkeypatch):
    game = tmp_path / "interactive.z3"
    # Echo the first byte of the accepted line, then quit.
    game.write_bytes(program_bytes(READ + bytes.fromhex("d0 1f 02 80 01 10 e5 bf 10 ba")))
    stream = io.StringIO("LOOK\r\nunused\n")
    monkeypatch.setattr(sys, "stdin", stream)
    assert _cli.main([str(game)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "\nl"
    assert captured.err == ""
    assert stream.readline() == "unused\n"


def test_cli_quit_during_startup_needs_no_input(tmp_path, capsys):
    game = tmp_path / "quit.z3"
    game.write_bytes(program_bytes(b"\xba"))
    assert _cli.main([str(game)]) == 0
    assert capsys.readouterr().err == ""


def test_cli_keyboard_interrupt_closes_without_traceback(tmp_path, capsys, monkeypatch):
    class InterruptedInput:
        def readline(self):
            raise KeyboardInterrupt

    game = tmp_path / "input.z3"
    game.write_bytes(program_bytes(READ))
    monkeypatch.setattr(sys, "stdin", InterruptedInput())
    assert _cli.main([str(game)]) == 130
    assert capsys.readouterr().err == ""


def test_cli_reports_execution_error_after_input(tmp_path, capsys, monkeypatch):
    game = tmp_path / "input.z3"
    game.write_bytes(program_bytes(READ + b"\xb0"))
    monkeypatch.setattr(sys, "stdin", io.StringIO("look\n"))
    assert _cli.main([str(game)]) == 1
    error = capsys.readouterr().err
    assert "initial execution context" in error
    assert "Traceback" not in error


def test_cli_execution_error_has_no_traceback(tmp_path, capsys):
    game = tmp_path / "bad-code.z3"
    game.write_bytes(program_bytes(b"\xb0"))
    assert _cli.main([str(game)]) == 1
    captured = capsys.readouterr()
    assert "rtrue at 0x401" in captured.err
    assert "Traceback" not in captured.err


def test_invalid_story_reports_error(tmp_path, capsys):
    game = tmp_path / "invalid.z3"
    game.write_bytes(b"invalid")
    assert _cli.main(["--inspect", str(game)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "64-byte header" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("version", range(1, 9))
def test_inspect_metadata(tmp_path, capsys, version):
    game = tmp_path / "misleading.z5"
    game.write_bytes(story_bytes(version))
    assert _cli.main(["--inspect", str(game)]) == 0
    captured = capsys.readouterr()
    metadata = json.loads(captured.out)
    assert metadata["version"] == version
    assert metadata["release"] == 42
    assert metadata["file_size"] == metadata["story_size"] == 4096
    assert metadata["entry_kind"] == ("routine" if version == 6 else "instruction")
    assert metadata["checksum_valid"] is (True if version >= 3 else None)
    assert captured.err == ""


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
