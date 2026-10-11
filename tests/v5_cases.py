"""Pinned V5 story identities and bounded startup scenarios."""

from pathlib import Path

STORY_905 = {
    "filename": "905.z5",
    "version": 5,
    "file_sha256": "0f41ff7811668e236060b399ced1cd0481c1bb624a8876fc7e16dc58816f1ecb",
}
SEED_905 = 42
ARCHIVE_905 = Path(__file__).parent / "vectors" / "905_vectors.zip"
STARTUP_ACTIONS = ("answer phone", "stand up", "s", "remove watch", "remove clothes")

CHECKPOINTS = (0, 5, 11, 18, 21, 22)
DETOURS = (
    "look",
    "inventory",
    "wait",
    "xyzzy",
    "flibbertigibbet",
    "take unicorn",
    "open unicorn",
    "kick door",
    "examine me",
    "examine watch",
    "drop watch",
    "wear watch",
    "open wallet",
    "look under bed",
    "sleep",
    "north",
    "east",
    "south",
    "west",
    "take all",
    "undo",
    "score",
)
SCENARIOS = (
    ("loss-and-restart", 21, ("no", "look", "restart", "answer phone")),
    ("victory-and-restart", 22, ("look", "restart", "stand up")),
    ("blocked-freeway", 18, ("enter car", "yes", "no", "yes")),
    (
        "office-detour",
        18,
        (
            "enter car",
            "no",
            "yes",
            "open wallet",
            "get id card",
            "put id card in slot",
            "w",
            "s",
            "look",
            "inventory",
        ),
    ),
    ("save-restore", 5, ("save", "wait", "n", "restore", "look", "inventory")),
    ("restart-confirmed", 5, ("restart", "yes", "look")),
    ("restart-cancelled", 5, ("restart", "no", "look")),
    ("quit-cancelled", 0, ("quit", "no", "look")),
    ("quit-confirmed", 0, ("quit", "yes")),
)
