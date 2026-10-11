"""Pinned V5 corpus and explicit reference startup conventions."""

from functools import lru_cache

from .story_corpus import GAMES as STORY_FILES
from .vector_archive import STORYFILES_PATH, read_archive

GAMES = tuple(name.removesuffix(".z5") for name in STORY_FILES[5])
SEED = 42
COMMANDS = ("look", "inventory", "wait", "flibbertigibbet", "take unicorn")
BOOT_ACTIONS = {
    "curses": ("",),
    "huntdark": ("", ""),
    "library": ("",),
    "loose": ("",),
    "sherlock": ("",),
    "theatre": ("",),
    "tryst205": ("",),
    # Public reset returns the introduction's observation, but its snapshot
    # includes these silent story commands. Measured via public RAM/input.
    "jewel": ("bypass", "yes"),
}
# These title screens paint the upper window. The original breadth adapter
# compares lower-window text, so its opening checks state only. Full-route
# comparisons include both windows. This is an explicit coverage boundary, not an automatic fallback.
WINDOWED_OPENINGS = frozenset({"curses", "huntdark", "library", "sherlock", "theatre"})


@lru_cache(maxsize=1)
def metadata():
    return read_archive(STORYFILES_PATH)


def story_identity(game):
    record = metadata()[f"{game}.z5.json"]
    assert record["header"]["version"] == 5
    return {
        "filename": f"{game}.z5",
        "version": 5,
        "file_sha256": record["file_sha256"],
    }
