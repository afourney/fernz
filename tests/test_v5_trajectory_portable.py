"""The full V5 trajectory suite replays on every supported host without Jericho."""

from pathlib import Path

import pytest

from .v5_trajectory_cases import GAMES
from .v5_trajectory_vectors import replay_trajectory
from .vector_archive import read_archive

pytestmark = [pytest.mark.rom, pytest.mark.vectors, pytest.mark.v5games]


@pytest.mark.parametrize("game", GAMES)
def test_v5_full_trajectory_portable(jericho_games, game):
    documents = read_archive(Path(__file__).parent / "vectors" / f"{game}_vectors.zip")
    replay_trajectory(jericho_games / f"{game}.z5", game, documents)
