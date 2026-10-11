"""Trinity's measured V4 identity, route and deterministic parser detours."""

from pathlib import Path

from .vector_archive import STORYFILES_PATH, read_archive

GAME = "trinity"
SEED = 0
ROUTE_LENGTH = 610
CHECKPOINTS = (0, 45, 150, 300, 450, 550)
COUNTERS = {"score": 154, "moves": 133}
COMMANDS = (
    "look",
    "inventory",
    "wait",
    "wait. wait",
    "score",
    "verbose",
    "brief",
    "flibbertigibbet",
    "qzxyzz",
    "xyzzy",
    "plugh",
    "",
    "LOOK",
    "look around",
    "take",
    "open",
    "put",
    "ask",
    "again",
    "oops",
    "take all",
    "drop all",
    "examine me",
    "kick door",
    "kick gate",
    "open watch",
    "eat coin",
    "put watch in coin",
    "put coin in watch",
    "take coin",
    "drop coin",
    "wear coin",
    "north",
    "south",
    "east",
    "west",
    "up",
    "down",
    "jump",
    "listen",
    "smell",
    *(
        f"{verb} {noun}"
        for verb in ("take", "open", "examine", "unlock")
        for noun in ("unicorn", "qzxyzz", "invisible teapot")
    ),
)


def archive_path():
    return Path(__file__).parent / "vectors" / "trinity_vectors.zip"


def story_identity():
    record = read_archive(STORYFILES_PATH)["trinity.z4.json"]
    assert record["header"]["version"] == 4
    return {"filename": "trinity.z4", "version": 4, "file_sha256": record["file_sha256"]}
