"""Live Linux counterparts of the portable V5 corpus startup tests."""

import pytest

from .scripts.v5_startup_vectors import startup_document
from .v5_corpus import GAMES
from .v5_corpus_vectors import replay_startup

pytestmark = [pytest.mark.reference, pytest.mark.v5games]


@pytest.mark.parametrize("game", GAMES)
def test_v5_corpus_startup_matches_live_reference(jericho_games, game):
    path = jericho_games / f"{game}.z5"
    replay_startup(path, game, startup_document(path, game))
