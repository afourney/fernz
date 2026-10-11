"""Linux public-API comparisons for the retained V8 stories."""

import pytest

from .scripts.v8_game_vectors import generate_v8
from .v8_cases import GAMES
from .v8_vectors import replay_opening

pytestmark = [pytest.mark.reference, pytest.mark.v8games]


@pytest.mark.parametrize("game", GAMES)
def test_v8_opening_matches_live_reference(jericho_games, game):
    path = jericho_games / f"{game}.z8"
    replay_opening(path, game, generate_v8(path, game))
