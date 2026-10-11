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
