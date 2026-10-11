"""Pinned V8 stories and measured public-reference startup conventions."""

from pathlib import Path

from .story_corpus import GAMES as CORPUS
from .vector_archive import STORYFILES_PATH, read_archive

GAMES = tuple(name.removesuffix(".z8") for name in CORPUS[8])
SEED = 42
BOOT_ACTIONS = {"anchor": ("", "", ""), "snacktime": ("",), "partyfoul": ("", "no")}
ROUTES = {
    "afflicted": {
        "length": 98,
        "score": 75,
        "max_score": 75,
        "player": 57,
        "objects": 238,
        "score_global": 26,
        "moves_global": 3,
    },
    "anchor": {
        "length": 531,
        "score": 99,
        "max_score": 100,
        "player": 20,
        "objects": 765,
        "score_global": 16,
        "moves_global": 4,
    },
    "lostpig": {
        "length": 146,
        "score": 6,
        "max_score": 7,
        "player": 87,
        "objects": 536,
        "score_global": 1,
        "moves_global": 2,
    },
    "snacktime": {
        "length": 34,
        "score": 50,
        "max_score": 50,
        "player": 44,
        "objects": 85,
        "score_global": 2,
        "moves_global": 3,
    },
    "partyfoul": {
        "length": 59,
        "score": 1,
        "max_score": 1,
        "player": 48,
        "objects": 142,
        "moves_global": 3,
    },
    "yomomma": {
        "length": 98,
        "score": 34,
        "max_score": 35,
        "player": 59,
        "objects": 140,
        "score_global": 2,
        "moves_global": 3,
    },
}


def archive_path(game):
    return Path(__file__).parent / "vectors" / f"{game}_vectors.zip"


def story_identity(game):
    record = read_archive(STORYFILES_PATH)[f"{game}.z8.json"]
    assert record["header"]["version"] == 8
    return {"filename": f"{game}.z8", "version": 8, "file_sha256": record["file_sha256"]}
