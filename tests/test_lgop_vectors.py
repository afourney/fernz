"""LGOP's portable trajectory, query API and branch coverage."""

import pytest

from .lgop_cases import STORY, archive_path, walkthrough
from .lgop_vectors import replay
from .vector_archive import read_archive


def test_lgop_archive_integrity_and_route_identity():
    documents = read_archive(archive_path())
    manifest = documents["manifest.json"]
    assert manifest["kind"] == "lgop-gameplay" and manifest["story"] == STORY
    steps = documents["walkthrough.json"]["cases"][0]["steps"]
    assert len(steps) == 390
    assert [row["action"] for row in steps[1:]] == walkthrough()


@pytest.mark.rom
@pytest.mark.vectors
@pytest.mark.v3games
@pytest.mark.parametrize("v3_game", ["lgop"])
def test_lgop_complete_route_detours_and_queries(jericho_games, v3_game):
    replay(jericho_games / f"{v3_game}.z3", read_archive(archive_path()))


@pytest.mark.rom
@pytest.mark.vectors
@pytest.mark.v3games
@pytest.mark.smoke
@pytest.mark.parametrize("v3_game", ["lgop"])
def test_lgop_opening_smoke(jericho_games, v3_game):
    replay(jericho_games / f"{v3_game}.z3", read_archive(archive_path()), smoke=True)
