"""Portable Trinity opening, parser detours and winning walkthrough."""

import pytest

from .v4_cases import archive_path, story_identity
from .v4_vectors import replay
from .vector_archive import REFERENCE_VERSION, read_archive


def test_v4_archive_integrity():
    documents = read_archive(archive_path())
    header = documents["manifest.json"]
    assert header["kind"] == "v4-game" and header["record_version"] == 1
    assert header["story"] == story_identity()
    assert header["boot_actions"] == [""]
    assert header["reference"]["version"] == REFERENCE_VERSION


@pytest.mark.rom
@pytest.mark.vectors
@pytest.mark.v4games
@pytest.mark.smoke
def test_v4_opening_and_five_commands(jericho_games):
    replay(jericho_games / "trinity.z4", read_archive(archive_path()), smoke=True)


@pytest.mark.rom
@pytest.mark.vectors
@pytest.mark.v4games
def test_v4_full_walkthrough_detours_and_lifecycle(jericho_games):
    replay(jericho_games / "trinity.z4", read_archive(archive_path()))
