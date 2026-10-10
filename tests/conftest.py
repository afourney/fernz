from pathlib import Path

import pytest

from .game_files import ensure_jericho_games


@pytest.fixture(scope="session")
def jericho_games() -> Path:
    """Provide the local Jericho ROM directory, downloading it if needed."""
    return ensure_jericho_games(Path(__file__).resolve().parents[1] / "games")
