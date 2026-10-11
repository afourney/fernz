"""Full V5 walkthroughs and profile probes through the public Linux reference."""

import pytest

from .scripts.v5_walkthrough_vectors import generate_walkthrough
from .v5_walkthrough_cases import GAMES
from .v5_walkthrough_vectors import replay_counters, replay_walkthrough

pytestmark = [pytest.mark.reference, pytest.mark.v5games]


@pytest.mark.parametrize("v5_game", GAMES)
def test_remaining_v5_walkthrough_matches_live_reference(jericho_games, v5_game):
    path = jericho_games / f"{v5_game}.z5"
    documents = generate_walkthrough(path, v5_game)
    replay_walkthrough(path, v5_game, documents)
    replay_counters(path, v5_game, documents["counters.json"])
