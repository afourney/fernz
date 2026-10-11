"""LGOP comparisons use documented public Jericho execution and snapshots."""

import pytest

from .lgop_vectors import replay
from .scripts.lgop_vectors import generate_lgop

pytestmark = [pytest.mark.reference, pytest.mark.v3games]


@pytest.mark.smoke
@pytest.mark.parametrize("v3_game", ["lgop"])
def test_lgop_opening_matches_jericho(jericho_games, tmp_path, monkeypatch, v3_game):
    monkeypatch.chdir(tmp_path)
    path = jericho_games / f"{v3_game}.z3"
    replay(path, generate_lgop(path, smoke=True), smoke=True)


@pytest.mark.parametrize("v3_game", ["lgop"])
def test_lgop_route_detours_and_queries_match_jericho(
    jericho_games, tmp_path, monkeypatch, v3_game
):
    monkeypatch.chdir(tmp_path)
    path = jericho_games / f"{v3_game}.z3"
    replay(path, generate_lgop(path))
