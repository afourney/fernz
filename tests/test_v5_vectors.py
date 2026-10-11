"""Portable V5 startup coverage using the same assertions as the live tests."""

import pytest

from fernz import FernzEnv

from .v5_cases import ARCHIVE_905, SEED_905, STORY_905
from .v5_vectors import check_step
from .vector_archive import REFERENCE_VERSION, digest, read_archive

pytestmark = [pytest.mark.rom, pytest.mark.vectors, pytest.mark.smoke]


def test_905_startup_commands_and_snapshot_continuation(jericho_games):
    documents = read_archive(ARCHIVE_905)
    manifest = documents["manifest.json"]
    assert manifest["story"] == STORY_905 and manifest["seed"] == SEED_905
    assert manifest["reference"]["version"] == REFERENCE_VERSION
    path = jericho_games / STORY_905["filename"]
    assert digest(path.read_bytes()) == STORY_905["file_sha256"]
    env = FernzEnv(path, seed=SEED_905)
    try:
        records = documents["startup.json"]["cases"][0]["steps"]
        check_step(env, records[0])
        opening = env.get_state()
        for record in records[1:]:
            before = env.get_state()
            check_step(env, record)
            expected = env.get_state()
            env.set_state(before)
            check_step(env, record)
            assert env.get_state() == expected
        check_step(env, records[0])
        assert env.get_state() == opening
    finally:
        env.close()
