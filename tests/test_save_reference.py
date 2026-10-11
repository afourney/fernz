"""Quetzal interchange through public APIs and executables; no source access."""

import subprocess

import pytest

from fernz import FernzEnv

from .save_story import save_story
from .test_reference import assert_zork_step
from .test_reference import zork1 as zork1
from .test_save_restore import Storage, results

pytestmark = pytest.mark.reference


def run_reference(binary, story, commands, *, load=None, seed=42):
    options = [binary, "-q", "-m", "-p", "-s", str(seed)]
    if load is not None:
        options += ["-L", str(load)]
    result = subprocess.run(
        [*options, str(story)],
        input="\n".join(commands) + "\n",
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stderr.strip() == "EOT", result.stderr
    return result.stdout


@pytest.mark.parametrize("high", [False, True], ids=["low-addresses", "high-addresses"])
def test_synthetic_quetzal_interchange_in_both_directions(dfrotz, tmp_path, high):
    story = tmp_path / "nested.z3"
    story.write_bytes(save_story(high=high))
    native_file = tmp_path / "native.qzl"
    native = run_reference(dfrotz, story, ["save", str(native_file), "continue"])
    expected = [7, 8, 9, 0x3333, 14545, 18, 42, 0x2222, 42, 0x1111]
    assert results(native) == expected

    storage = Storage()
    env = FernzEnv(
        story, seed=42, save_handler=storage.save, restore_handler=native_file.read_bytes
    )
    try:
        env.reset()
        imported = env.step("restore")[0] + env.step("continue")[0]
        assert results(imported) == expected
        env.reset()
        exported = env.step("save")[0] + env.step("continue")[0]
        assert results(exported) == expected
        fernz_file = tmp_path / "fernz.qzl"
        fernz_file.write_bytes(storage.data)
        restored = run_reference(dfrotz, story, ["continue"], load=fernz_file)
        assert results(restored) == expected
    finally:
        env.close()


def test_zork_quetzal_files_work_in_both_interpreters(dfrotz, zork1, tmp_path):
    prefix = ["open mailbox", "take leaflet"]
    suffix = ["inventory", "read leaflet", "north", "east", "open window", "enter", "look"]
    native_file = tmp_path / "native.qzl"
    run_reference(dfrotz, zork1, [*prefix, "save", str(native_file)], seed=12)

    storage = Storage()
    donor = FernzEnv(zork1, seed=12, save_handler=storage.save)
    try:
        donor.reset()
        for action in prefix:
            donor.step(action)
        saved = donor.step("save")
        assert saved[0] == "\nOk.\n\n>"
        expected = [donor.step(action) for action in suffix]
        assert "A leaflet" in expected[0][0]
        assert expected[-1][3] == {"score": 10, "moves": 9}
    finally:
        donor.close()
    fernz_file = tmp_path / "fernz.qzl"
    fernz_file.write_bytes(storage.data)

    # The recipient processes start fresh; neither replays the donor's prefix.
    # Compare complete native transcripts with identical display settings, so
    # wrapping and status lines need no normalization between these two runs.
    assert run_reference(dfrotz, zork1, suffix, load=fernz_file, seed=12) == run_reference(
        dfrotz, zork1, suffix, load=native_file, seed=12
    )
    for file in (native_file, fernz_file):
        env = FernzEnv(zork1, seed=12, restore_handler=file.read_bytes)
        try:
            env.reset()
            assert env.step("restore") == saved
            assert [env.step(action) for action in suffix] == expected
        finally:
            env.close()


def test_zork_fernz_save_restores_in_jericho(zork1, tmp_path, monkeypatch):
    from jericho import FrotzEnv

    story = zork1.resolve()
    # Measured through public step calls: Jericho 3.3.1 uses this default
    # filename without prompting. Isolate its file access from other tests.
    monkeypatch.chdir(tmp_path)
    storage = Storage()
    donor = FernzEnv(story, seed=12, save_handler=storage.save)
    try:
        donor.reset()
        donor.step("open mailbox")
        donor.step("take leaflet")
        saved = donor.step("save")
        (tmp_path / "zork1.qzl").write_bytes(storage.data)

        reference = FrotzEnv(str(story), seed=12)
        try:
            assert reference.reset()[1] == {"score": 0, "moves": 0}
            assert_zork_step(saved, reference.step("restore"), final=False)
            actions = ["inventory", "read leaflet", "north", "east", "open window", "enter", "look"]
            for action in actions:
                actual = donor.step(action)
                expected = reference.step(action)
                assert_zork_step(actual, expected, final=False)
                if action == "inventory":
                    assert "A leaflet" in expected[0]
            assert expected[3] == {"score": 10, "moves": 9}
        finally:
            reference.close()
    finally:
        donor.close()
