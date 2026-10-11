"""Portable full-route and API coverage from hashed public-reference vectors."""

from pathlib import Path

import pytest

from .v5_walkthrough_cases import GAMES
from .v5_walkthrough_vectors import replay_counters, replay_walkthrough
from .vector_archive import read_archive

pytestmark = [pytest.mark.rom, pytest.mark.vectors, pytest.mark.v5games]


@pytest.mark.parametrize("v5_game", GAMES)
def test_remaining_v5_walkthrough_portable(jericho_games, v5_game):
    documents = read_archive(Path(__file__).parent / "vectors" / f"{v5_game}_vectors.zip")
    replay_walkthrough(jericho_games / f"{v5_game}.z5", v5_game, documents)


@pytest.mark.parametrize("v5_game", GAMES)
def test_v5_profile_counter_widths_portable(jericho_games, v5_game):
    document = read_archive(Path(__file__).parent / "vectors" / f"{v5_game}_vectors.zip")
    replay_counters(jericho_games / f"{v5_game}.z5", v5_game, document["counters.json"])
