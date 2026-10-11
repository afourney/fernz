"""Every retained story needs measured query metadata and a recorded winning route."""

import json
from functools import lru_cache
from pathlib import Path
from zipfile import ZipFile

import pytest

from fernz._profiles import _PROFILES

from .story_corpus import GAMES
from .vector_archive import STORYFILES_PATH, digest, read_archive


@lru_cache(maxsize=1)
def story_metadata():
    return read_archive(STORYFILES_PATH)


@pytest.mark.parametrize("filename", [name for games in GAMES.values() for name in games])
def test_every_story_has_profile_and_winning_route(filename):
    metadata = story_metadata()[f"{filename}.json"]
    profile = _PROFILES[metadata["memory_sha256"]]
    assert profile.player_object is not None and profile.player_object > 0
    assert profile.victory_lines or profile.victory_hashes
    if filename == "lgop.z3":
        assert profile.max_score is None  # Randomized scoring has no fixed maximum.
    else:
        assert profile.max_score is not None and profile.max_score > 0

    path = Path(__file__).parent / "vectors" / f"{Path(filename).stem}_vectors.zip"
    # Inspect only the route here; game-specific integrity tests check every member.
    with ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        payload = archive.read("walkthrough.json")
    assert digest(payload) == manifest["files"]["walkthrough.json"]["sha256"]
    hash_field = "sha256" if filename == "zork1.z5" else "file_sha256"
    assert manifest["story"][hash_field] == metadata["file_sha256"]
    routes = json.loads(payload)["cases"]
    assert routes
    for route in routes:
        assert isinstance(route.get("seed", manifest.get("seed")), int)
        first, *turns = route["steps"]
        assert first["action"] is None and turns
        assert all(isinstance(turn["action"], str) for turn in turns)
        queries = turns[-1]["queries"]
        assert queries["victory"] is True
        assert isinstance(queries["score"], int) and isinstance(queries["moves"], int)
        if filename != "lgop.z3":
            assert queries["max_score"] == profile.max_score
        if "player" in queries:
            assert queries["player"] == profile.player_object
