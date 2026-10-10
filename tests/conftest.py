import os
import shutil
from pathlib import Path

import pytest

from .game_files import ensure_jericho_games


@pytest.fixture(scope="session")
def jericho_games() -> Path:
    """Provide the local Jericho ROM directory, downloading it if needed."""
    return ensure_jericho_games(Path(__file__).resolve().parents[1] / "games")


@pytest.fixture(scope="session")
def dfrotz():
    """Locate the required external reference executable without inspecting it."""
    executable = os.environ.get("FERNZ_DFROTZ") or shutil.which("dfrotz") or "/usr/games/dfrotz"
    if not Path(executable).is_file() or not os.access(executable, os.X_OK):
        pytest.fail("Install the frotz binary package or set FERNZ_DFROTZ to the dfrotz executable")
    return executable
