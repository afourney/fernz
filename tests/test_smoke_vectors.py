"""Bounded gameplay checks without full-route fixtures or a native reference."""

from pathlib import Path

import pytest

from fernz import FernzEnv

from .test_zork_vectors import step_and_check as check_zork
from .v3_cases import GAMES
from .v3_vectors import step_and_check as check_v3
from .vector_archive import REFERENCE_VERSION, digest, read_archive
from .zork_scenarios import WALKTHROUGH_SEED, ZORK1_SHA256

pytestmark = [pytest.mark.rom, pytest.mark.vectors, pytest.mark.smoke]


@pytest.mark.parametrize("game", ("zork1", *GAMES))
def test_opening_five_commands_copy_restore_and_reset(jericho_games, game):
    # Reading the whole archive verifies every member's hash, but executing
    # only this fixed prefix avoids the expensive walkthrough-state fixtures.
    documents = read_archive(Path(__file__).parent / "vectors" / f"{game}_vectors.zip")
    manifest = documents["manifest.json"]
    assert manifest["reference"]["version"] == REFERENCE_VERSION
    assert manifest["state_format_version"] == 2
    if game == "zork1":
        filename, seed, checksum = "zork1.z5", WALKTHROUGH_SEED, ZORK1_SHA256
        assert manifest["story"] == {"filename": filename, "version": 3, "sha256": checksum}
    else:
        assert manifest["story"] == GAMES[game]
        filename = GAMES[game]["filename"]
        seed, checksum = GAMES[game]["seed"], GAMES[game]["file_sha256"]
    assert manifest["seed"] == seed
    path = jericho_games / filename
    assert digest(path.read_bytes()) == checksum
    records = documents["walkthrough.json"]["cases"][0]["steps"][:6]
    assert len(records) == 6 and records[0]["action"] is None

    def check(env, record):
        if game == "zork1":
            check_zork(env, record)
        else:
            check_v3(env, record, game)

    env = FernzEnv(path, seed=seed)
    fork = None
    try:
        for record in records[:-1]:
            check(env, record)
        before = env.get_state()
        fork = env.copy()
        check(fork, records[-1])
        assert env.get_state() == before
        check(env, records[-1])
        expected = env.get_state()
        assert fork.get_state() == expected
        env.set_state(before)
        check(env, records[-1])
        assert env.get_state() == expected
        check(env, records[0])
    finally:
        if fork is not None:
            fork.close()
        env.close()
