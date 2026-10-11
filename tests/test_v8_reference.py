"""Linux public-API comparisons for the retained V8 stories."""

import pytest

from .scripts.v8_game_vectors import generate_v8
from .v8_cases import GAMES, ROUTES
from .v8_vectors import replay_actions, replay_opening
from .v8_walkthrough_vectors import replay_counters, replay_walkthrough

pytestmark = [pytest.mark.reference, pytest.mark.v8games]


@pytest.mark.parametrize("game", GAMES)
def test_v8_opening_and_actions_match_live_reference(jericho_games, game, tmp_path, monkeypatch):
    path = jericho_games / f"{game}.z8"
    monkeypatch.chdir(tmp_path)
    documents = generate_v8(path, game)
    replay_opening(path, game, documents)
    replay_actions(path, game, documents)


@pytest.mark.parametrize("game", ROUTES)
def test_v8_winning_route_matches_live_reference(jericho_games, game, tmp_path, monkeypatch):
    path = jericho_games / f"{game}.z8"
    monkeypatch.chdir(tmp_path)
    documents = generate_v8(path, game)
    replay_walkthrough(path, game, documents)
    replay_counters(path, game, documents["counters.json"])
