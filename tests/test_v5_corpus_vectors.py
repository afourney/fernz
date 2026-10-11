"""All retained V5 stories: bounded portable startup and command coverage."""

from pathlib import Path

import pytest

from .v5_corpus import BOOT_ACTIONS, GAMES, story_identity
from .v5_corpus_vectors import replay_startup
from .vector_archive import REFERENCE_VERSION, read_archive

pytestmark = [pytest.mark.rom, pytest.mark.vectors, pytest.mark.v5games]


@pytest.mark.parametrize("game", GAMES)
def test_v5_corpus_startup(jericho_games, game):
    archive = Path(__file__).parent / "vectors" / f"{game}_vectors.zip"
    documents = read_archive(archive)
    manifest = documents["manifest.json"]
    assert manifest["story"] == story_identity(game)
    assert manifest["reference"]["version"] == REFERENCE_VERSION
    if game != "905":
        kind = "v5-trajectory" if game in ("balances", "sherlock") else "v5-walkthrough"
        assert manifest["kind"] == kind and manifest["record_version"] == 1
        assert manifest["boot_actions"] == list(BOOT_ACTIONS.get(game, ()))
    replay_startup(jericho_games / f"{game}.z5", game, documents["breadth.json"])
