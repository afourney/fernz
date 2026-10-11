import os
import shutil
from pathlib import Path

import pytest

from .game_files import ensure_jericho_games
from .v3_cases import GAMES as V3_GAMES


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


def pytest_addoption(parser):
    parser.addoption(
        "--v3-shard", help="Select a disjoint part of the additional V3 games, e.g. 1/3"
    )

    parser.addoption("--v5-shard", help="Select a disjoint part of the V5 games, e.g. 1/3")


def pytest_collection_modifyitems(config, items):
    from .v3_cases import selected_games
    from .v5_shards import selected_games as selected_v5_games

    try:
        selected = selected_games(config.getoption("--v3-shard"))
        selected_v5 = selected_v5_games(config.getoption("--v5-shard"))
    except ValueError as error:
        raise pytest.UsageError(str(error)) from error
    kept, removed = [], []
    for item in items:
        game = item.callspec.params.get("v3_game") if hasattr(item, "callspec") else None
        params = item.callspec.params if hasattr(item, "callspec") else {}
        v5 = params.get("v5_game")
        if v5 is None and item.get_closest_marker("v5games"):
            v5 = params.get("game")
        retain = (game is None or game in selected) and (v5 is None or v5 in selected_v5)
        (kept if retain else removed).append(item)
    if removed:
        config.hook.pytest_deselected(items=removed)
        items[:] = kept


@pytest.fixture(scope="module", params=V3_GAMES)
def v3_game(request):
    return request.param
