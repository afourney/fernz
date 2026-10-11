"""Portable V8 openings; the same assertions run against the live reference."""

import pytest

from .v8_cases import BOOT_ACTIONS, GAMES, archive_path, story_identity
from .v8_vectors import replay_actions, replay_opening
from .vector_archive import REFERENCE_VERSION, read_archive


@pytest.mark.parametrize("game", GAMES)
def test_v8_archive_integrity(game):
    header = read_archive(archive_path(game))["manifest.json"]
    assert header["kind"] == "v8-game" and header["record_version"] == 1
    assert header["story"] == story_identity(game)
    assert header["boot_actions"] == list(BOOT_ACTIONS.get(game, ()))
    assert header["reference"]["version"] == REFERENCE_VERSION


@pytest.mark.rom
@pytest.mark.vectors
@pytest.mark.v8games
@pytest.mark.parametrize(
    "game",
    [pytest.param(game, marks=pytest.mark.smoke) if game == "lostpig" else game for game in GAMES],
)
def test_v8_opening(jericho_games, game):
    replay_opening(jericho_games / f"{game}.z8", game, read_archive(archive_path(game)))


@pytest.mark.rom
@pytest.mark.vectors
@pytest.mark.v8games
@pytest.mark.parametrize("game", GAMES)
def test_v8_actions_and_persistence(jericho_games, game):
    replay_actions(jericho_games / f"{game}.z8", game, read_archive(archive_path(game)))
