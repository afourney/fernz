"""V4 public-API comparisons and independent Quetzal interchange probes."""

import pytest

from fernz import FernzEnv

from .observation_helpers import plain_text
from .scripts.v4_game_vectors import generate_v4
from .test_restart_reference import synthetic_reference
from .test_save_reference import run_reference
from .test_save_restore import Storage
from .v4_story import save_story
from .v4_vectors import replay

pytestmark = [pytest.mark.reference, pytest.mark.v4games]


@pytest.mark.smoke
def test_v4_opening_and_five_commands_match_jericho(jericho_games, tmp_path, monkeypatch):
    path = jericho_games / "trinity.z4"
    monkeypatch.chdir(tmp_path)
    replay(path, generate_v4(path, smoke=True), smoke=True)


def test_v4_walkthrough_detours_and_lifecycle_match_jericho(jericho_games, tmp_path, monkeypatch):
    path = jericho_games / "trinity.z4"
    monkeypatch.chdir(tmp_path)
    replay(path, generate_v4(path))


@pytest.mark.parametrize("store", (0, 8))
@pytest.mark.parametrize("high", (False, True))
def test_v4_quetzal_interchange_with_jericho(tmp_path, monkeypatch, store, high):
    path = tmp_path / "probe.z4"
    path.write_bytes(save_story(store=store, high=high))
    monkeypatch.chdir(tmp_path)
    reference = synthetic_reference(path, 42)
    storage = Storage()
    env = FernzEnv(path, seed=42, save_handler=storage.save, restore_handler=storage.restore)
    try:
        reference.reset()
        assert plain_text(reference.step("save")[0]) == "\n1\n"
        storage.data = (tmp_path / "probe.qzl").read_bytes()
        env.reset()
        assert env.step("restore")[0].text == "\n2\n"
        assert env.step("continue")[0].text == "\n8738\n7\n"
        env.reset()
        assert env.step("save")[0].text == "\n1\n"
        (tmp_path / "probe.qzl").write_bytes(storage.data)
        reference.reset()
        assert plain_text(reference.step("restore")[0]) == "\n2\n"
        assert plain_text(reference.step("continue")[0]) == "\n8738\n7\n"
    finally:
        env.close()
        reference.close()


def test_v4_quetzal_interchange_with_frotz(dfrotz, tmp_path):
    path = tmp_path / "probe.z4"
    path.write_bytes(save_story(high=True))
    native = tmp_path / "native.qzl"
    output = run_reference(dfrotz, path, ["save", str(native), "continue"])
    assert "]: 1\n" in output and "8738\n7\n" in output
    storage = Storage()
    env = FernzEnv(path, seed=42, save_handler=storage.save, restore_handler=native.read_bytes)
    try:
        env.reset()
        assert env.step("restore")[0].text == "\n2\n"
        assert env.step("continue")[0].text == "\n8738\n7\n"
        env.reset()
        env.step("save")
        exported = tmp_path / "fernz.qzl"
        exported.write_bytes(storage.data)
        assert "8738\n7\n" in run_reference(dfrotz, path, ["continue"], load=exported)
    finally:
        env.close()
