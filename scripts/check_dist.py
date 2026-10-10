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
        for required in ("fernz/__init__.py", "fernz/py.typed"):
            assert required in names, f"Missing from wheel: {required}"
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = email.message_from_bytes(wheel.read(metadata_name))
        assert metadata["Name"] == project["name"], "Incorrect distribution name"
        assert metadata["Version"] == project["version"], "Incorrect distribution version"
        check_no_games(names)

    with tarfile.open(sdists[0], "r:gz") as sdist:
        names = sdist.getnames()
        relative_names = {"/".join(PurePosixPath(name).parts[1:]) for name in names}
        for required in ("pyproject.toml", "src/fernz/__init__.py", "src/fernz/py.typed"):
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
                    "import importlib.metadata, pathlib, sys, fernz; "
                    "assert importlib.metadata.version('fernz') == sys.argv[1]; "
                    "assert pathlib.Path(fernz.__file__).is_relative_to(pathlib.Path(sys.prefix))"
                ),
                project["version"],
            ],
            cwd=tmp,
            check=True,
            timeout=15,
        )
    print("Validated wheel and source distribution; isolated wheel import passed.")


if __name__ == "__main__":
    main()
