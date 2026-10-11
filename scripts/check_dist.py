"""Validate built distributions and smoke-test an isolated wheel installation."""

import email
import os
import shutil
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def check_no_games(names: list[str]) -> None:
    """Reject downloaded game files in either distribution format."""
    for name in names:
        path = PurePosixPath(name)
        assert "games" not in path.parts, f"Game data must not be packaged: {name}"
        assert path.suffix.lower() not in {f".z{version}" for version in range(1, 9)}, (
            f"Story files must not be packaged: {name}"
        )


def main() -> None:
    """Check package contents, metadata, and importability from the built wheel."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    wheels = list((ROOT / "dist").glob("*.whl"))
    sdists = list((ROOT / "dist").glob("*.tar.gz"))
    assert len(wheels) == len(sdists) == 1, "Expected one wheel and one source distribution"
    wheel_path = wheels[0]
    assert wheel_path.name.endswith("-py3-none-any.whl"), "Expected a pure Python wheel"

    with ZipFile(wheel_path) as wheel:
        names = wheel.namelist()
        for required in (
            "fernz/__init__.py",
            "fernz/_env.py",
            "fernz/_story.py",
            "fernz/_memory.py",
            "fernz/_errors.py",
            "fernz/_instruction.py",
            "fernz/_input.py",
            "fernz/_opcodes.py",
            "fernz/_text.py",
            "fernz/_objects.py",
            "fernz/_output.py",
            "fernz/_observation.py",
            "fernz/_profiles.py",
            "fernz/_machine.py",
            "fernz/_random.py",
            "fernz/_state.py",
            "fernz/_quetzal.py",
            "fernz/_host_io.py",
            "fernz/_cli.py",
            "fernz/_simple_cli.py",
            "fernz/_rich_cli.py",
            "fernz/_screen.py",
            "fernz/_cli_files.py",
            "fernz/__main__.py",
            "fernz/py.typed",
        ):
            assert required in names, f"Missing from wheel: {required}"
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = email.message_from_bytes(wheel.read(metadata_name))
        assert metadata["Name"] == project["name"], "Incorrect distribution name"
        assert metadata["Version"] == project["version"], "Incorrect distribution version"
        assert "textual" in metadata.get_all("Provides-Extra", [])
        requirements = metadata.get_all("Requires-Dist", [])
        assert requirements and all(
            value.partition(";")[2].strip().replace("'", '"') == 'extra == "textual"'
            for value in requirements
        ), "Runtime dependencies must be confined to the optional Textual extra"
        check_no_games(names)

    with tarfile.open(sdists[0], "r:gz") as sdist:
        names = sdist.getnames()
        relative_names = {"/".join(PurePosixPath(name).parts[1:]) for name in names}
        for required in (
            "pyproject.toml",
            "src/fernz/__init__.py",
            "src/fernz/_env.py",
            "src/fernz/_story.py",
            "src/fernz/_memory.py",
            "src/fernz/_errors.py",
            "src/fernz/_instruction.py",
            "src/fernz/_input.py",
            "src/fernz/_opcodes.py",
            "src/fernz/_text.py",
            "src/fernz/_objects.py",
            "src/fernz/_output.py",
            "src/fernz/_observation.py",
            "src/fernz/_profiles.py",
            "src/fernz/_machine.py",
            "src/fernz/_random.py",
            "src/fernz/_state.py",
            "src/fernz/_quetzal.py",
            "src/fernz/_host_io.py",
            "src/fernz/_cli.py",
            "src/fernz/_simple_cli.py",
            "src/fernz/_rich_cli.py",
            "src/fernz/_screen.py",
            "src/fernz/_cli_files.py",
            "src/fernz/__main__.py",
            "src/fernz/py.typed",
        ):
            assert required in relative_names, f"Missing from source distribution: {required}"
        check_no_games(names)

    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv is required to check the installed wheel")
    with TemporaryDirectory(prefix="fernz-wheel-check-") as tmp:
        environment = Path(tmp) / "venv"
        subprocess.run([uv, "venv", "--python", sys.executable, str(environment)], check=True)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [uv, "pip", "install", "--python", str(python), str(wheel_path)],
            check=True,
            timeout=120,
        )
        # Isolated mode and an external working directory prevent an editable
        # checkout from concealing missing files in the actual wheel.
        subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                (
                    "import importlib.metadata, importlib.util, pathlib, sys, fernz; "
                    "assert importlib.util.find_spec('textual') is None; "
                    "assert importlib.metadata.version('fernz') == sys.argv[1]; "
                    "assert pathlib.Path(fernz.__file__).is_relative_to(pathlib.Path(sys.prefix))"
                ),
                project["version"],
            ],
            cwd=tmp,
            check=True,
            timeout=15,
        )
        command = environment / ("Scripts/fernz.exe" if os.name == "nt" else "bin/fernz")
        game = Path(tmp) / "test game.z3"
        # An independent executable V3 fixture; no compiler or game text needed.
        data = bytearray(4096)
        data[0] = 3
        for address, value in (
            (4, 0x400),
            (6, 0x401),
            (8, 0x300),
            (10, 0x40),
            (12, 0x100),
            (14, 0x300),
            (0x1A, 2048),
        ):
            data[address : address + 2] = value.to_bytes(2, "big")
        # Print the opening, read a command, print its first character, then quit.
        code = bytes.fromhex("e5 7f 41 bb e5 7f 3e e4 0f 02 80 02 a0 d0 1f 02 80 01 10 e5 bf 10 ba")
        data[0x401 : 0x401 + len(code)] = code
        data[0x280], data[0x2A0] = 20, 4
        data[0x301] = 4  # Empty dictionary.
        data[0x1C:0x1E] = (sum(data[64:]) & 0xFFFF).to_bytes(2, "big")
        game.write_bytes(data)
        # Exercise both installed entry points outside the checkout, including
        # path validation, inspection, and an interactive input/quit cycle.
        for entry_point in ([str(command)], [str(python), "-I", "-m", "fernz"]):
            for args, code, message in (
                (["--help"], 0, "usage: fernz"),
                ([str(Path(tmp) / "missing.z3")], 2, "fernz:"),
                (["--inspect", str(game)], 0, '"version": 3'),
                ([str(game)], 0, "A\n>\nl"),
                (["--simple", str(game)], 0, "A\n>\nl"),
                (["--rich", str(game)], 2, "pip install 'fernz[textual]'"),
            ):
                result = subprocess.run(
                    [*entry_point, *args],
                    cwd=tmp,
                    capture_output=True,
                    text=True,
                    input="LOOK\n",
                    timeout=15,
                )
                assert result.returncode == code, result
                output = result.stdout if code == 0 else result.stderr
                assert message in output, result
                assert "Traceback" not in result.stderr, result
    print("Validated distributions; isolated wheel import and CLI checks passed.")


if __name__ == "__main__":
    main()
