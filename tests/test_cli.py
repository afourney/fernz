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
    # OSError repr-quotes filenames, including backslashes on Windows;
    # the explicit directory validation prints the path directly.
    expected_path = str(path) if directory else repr(str(path))
    assert expected_path in captured.err
    assert "Traceback" not in captured.err


def test_existing_game_reports_unimplemented(tmp_path, capsys):
    game = tmp_path / "game with spaces.z3"
    game.write_bytes(story_bytes(7))
    assert _cli.main([str(game)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "supports V3, V5 and V8" in captured.err
    assert "Traceback" not in captured.err
    assert game.read_bytes() == story_bytes(7)


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


def test_cli_continues_after_story_restart_without_an_extra_confirmation(
    tmp_path, capsys, monkeypatch
):
    game = tmp_path / "restart.z3"
    # Print A and read; print B and restart. Only the story controls prompts.
    game.write_bytes(program_bytes(bytes.fromhex("e5 7f 41") + READ + bytes.fromhex("e5 7f 42 b7")))
    monkeypatch.setattr(sys, "stdin", io.StringIO("again\nagain\n"))
    assert _cli.main([str(game)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "A\nBA\nBA"
    assert captured.err == ""


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


@pytest.mark.parametrize("width,height", [(80, 25), (128, 232)])
def test_cli_delegates_to_library_and_closes(tmp_path, monkeypatch, capsys, width, height):
    calls = []

    class StubEnv:
        def __init__(self, path, **handlers):
            calls.append(("init", path))
            assert handlers.pop("screen_width") == width
            assert handlers.pop("screen_height") == height
            assert set(handlers) == {"save_handler", "restore_handler", "output_handler"}
            assert all(callable(handler) for handler in handlers.values())

        def reset(self):
            calls.append("reset")
            raise NotImplementedError("test execution unavailable")

        def close(self):
            calls.append("close")

    monkeypatch.setattr(_cli, "FernzEnv", StubEnv)
    game = tmp_path / "game.z3"
    args = [str(game)]
    if (width, height) != (80, 25):
        args += ["--screen-width", str(width), "--screen-height", str(height)]
    assert _cli.main(args) == 1
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


@pytest.fixture
def saving_game(tmp_path):
    game = tmp_path / "save.z3"
    # Print P before the host prompt; then print S or F according to the save.
    game.write_bytes(program_bytes(bytes.fromhex("e5 7f 50 b5 c6 e5 7f 46 ba e5 7f 53 ba")))
    return game


def test_save_prompt_streams_prior_output_and_writes_quetzal(
    saving_game, tmp_path, capsys, monkeypatch
):
    path = tmp_path / "saved game.qzl"
    monkeypatch.setattr(sys, "stdin", io.StringIO(str(path) + "\n"))
    assert _cli.main([str(saving_game)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "PSave file (blank cancels): S"
    assert captured.err == ""
    assert path.read_bytes()[:12].startswith(b"FORM")
    assert path.read_bytes()[8:12] == b"IFZS"


@pytest.mark.parametrize("answer", ["\n", ""])
def test_save_cancellation_and_eof_report_opcode_failure(saving_game, capsys, monkeypatch, answer):
    monkeypatch.setattr(sys, "stdin", io.StringIO(answer))
    assert _cli.main([str(saving_game)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "PSave file (blank cancels): F"
    assert captured.err == ""


@pytest.mark.parametrize("answer,overwrite", [("yes", True), ("no", False), ("", False)])
def test_save_overwrite_requires_confirmation(
    saving_game, tmp_path, capsys, monkeypatch, answer, overwrite
):
    path = tmp_path / "existing.qzl"
    path.write_bytes(b"original")
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{path}\n{answer}\n"))
    assert _cli.main([str(saving_game)]) == 0
    captured = capsys.readouterr()
    assert "Overwrite existing file?" in captured.out
    assert captured.out.endswith("S" if overwrite else "F")
    assert captured.err == ""
    assert (path.read_bytes() != b"original") is overwrite
    assert not list(tmp_path.glob(".existing.qzl.*"))


def test_failed_atomic_save_keeps_existing_file(saving_game, tmp_path, capsys, monkeypatch):
    path = tmp_path / "existing.qzl"
    path.write_bytes(b"original")
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{path}\ny\n"))

    def fail(*_):
        raise OSError("write unavailable")

    monkeypatch.setattr(_cli.os, "replace", fail)
    assert _cli.main([str(saving_game)]) == 0
    captured = capsys.readouterr()
    assert captured.out.endswith("F")
    assert "write unavailable" in captured.err
    assert path.read_bytes() == b"original"
    assert not list(tmp_path.glob(".existing.qzl.*"))


@pytest.mark.parametrize("kind", ["missing", "corrupt", "cancel", "eof"])
def test_restore_failure_returns_control_to_game(tmp_path, capsys, monkeypatch, kind):
    game = tmp_path / "restore.z3"
    game.write_bytes(program_bytes(bytes.fromhex("b6 c6 e5 7f 46 ba e5 7f 54 ba")))
    path = tmp_path / "save.qzl"
    if kind == "corrupt":
        path.write_bytes(b"corrupt")
    answer = "\n" if kind == "cancel" else "" if kind == "eof" else f"{path}\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(answer))
    assert _cli.main([str(game)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "Restore file (blank cancels): F"
    assert ("fernz:" in captured.err) is (kind == "missing")


def test_cli_save_and_restore_in_separate_processes(tmp_path):
    from .save_story import save_story
    from .test_save_restore import results

    game = tmp_path / "story with spaces.z3"
    save = tmp_path / "state with spaces.qzl"
    game.write_bytes(save_story())
    for command in ("save", "restore"):
        result = subprocess.run(
            [sys.executable, "-m", "fernz", str(game)],
            input=f"{command}\n{save}\ncontinue\n",
            text=True,
            capture_output=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        numbers = results(result.stdout)
        # RNG is intentionally not portable; verify every deterministic value.
        assert numbers[:4] == [7, 8, 9, 0x3333]
        assert 1 <= numbers[4] <= 32767
        assert numbers[5:] == [18, 42, 0x2222, 42, 0x1111]
