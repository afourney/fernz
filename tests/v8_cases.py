"""Pinned V8 stories and measured public-reference startup conventions."""

from pathlib import Path

from .story_corpus import GAMES as CORPUS
from .vector_archive import STORYFILES_PATH, read_archive

GAMES = tuple(name.removesuffix(".z8") for name in CORPUS[8])
SEED = 42
BOOT_ACTIONS = {"anchor": ("", "", ""), "snacktime": ("",), "partyfoul": ("", "no")}


def archive_path(game):
    return Path(__file__).parent / "vectors" / f"{game}_vectors.zip"


def story_identity(game):
    record = read_archive(STORYFILES_PATH)[f"{game}.z8.json"]
    assert record["header"]["version"] == 8
    return {"filename": f"{game}.z8", "version": 8, "file_sha256": record["file_sha256"]}
