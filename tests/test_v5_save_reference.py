"""V5 Quetzal interoperability through public reference interfaces."""

import re

import pytest

from fernz import FernzEnv

from .observation_helpers import plain_text, window_text
from .test_restart_reference import synthetic_reference
from .test_save_reference import run_reference
from .test_save_restore import Storage
from .v5_cases import SEED_905, STORY_905
from .v5_story import save_story
from .v5_vectors import capture_reference, check_step

pytestmark = pytest.mark.reference


def results(text):
    return [int(value) for value in re.findall(r"(?m)^(\d+)$", text)]


@pytest.mark.parametrize("store", (0, 8))
@pytest.mark.parametrize("high", (False, True))
def test_v5_quetzal_interchange_with_jericho(tmp_path, monkeypatch, store, high):
    path = tmp_path / "probe.z5"
    path.write_bytes(save_story(store=store, high=high))
    monkeypatch.chdir(tmp_path)
    reference = synthetic_reference(path, SEED_905)
    storage = Storage()
    env = FernzEnv(path, seed=SEED_905, save_handler=storage.save, restore_handler=storage.restore)
    try:
        reference.reset()
        assert plain_text(reference.step("save")[0]) == "\n1\n"
        storage.data = (tmp_path / "probe.qzl").read_bytes()
        env.reset()
        assert plain_text(env.step("restore")[0]) == "\n2\n"
        assert results(plain_text(env.step("continue")[0])) == [8738, 77]
        assert results(plain_text(reference.step("continue")[0])) == [8738, 77]
        env.reset()
        assert plain_text(env.step("save")[0]) == "\n1\n"
        (tmp_path / "probe.qzl").write_bytes(storage.data)
        reference.reset()
        assert plain_text(reference.step("restore")[0]) == "\n2\n"
        assert results(plain_text(reference.step("continue")[0])) == [8738, 77]
    finally:
        env.close()
        reference.close()


@pytest.mark.parametrize("high", (False, True))
def test_v5_quetzal_interchange_with_frotz(dfrotz, tmp_path, high):
    path = tmp_path / "probe.z5"
    path.write_bytes(save_story(high=high))
    native = tmp_path / "native.qzl"
    output = run_reference(dfrotz, path, ["save", str(native), "continue"])
    assert "]: 1\n" in output and results(output) == [8738, 77]
    storage = Storage()
    env = FernzEnv(path, seed=42, save_handler=storage.save, restore_handler=native.read_bytes)
    env.reset()
    assert plain_text(env.step("restore")[0]) == "\n2\n"
    assert results(plain_text(env.step("continue")[0])) == [8738, 77]
    env.reset()
    env.step("save")
    exported = tmp_path / "fernz.qzl"
    exported.write_bytes(storage.data)
    assert results(run_reference(dfrotz, path, ["continue"], load=exported)) == [2, 8738, 77]


@pytest.mark.parametrize("donor", ("fernz", "jericho"))
def test_905_files_transfer_midgame_and_continue_to_victory(
    jericho_games, tmp_path, monkeypatch, donor
):
    from jericho import FrotzEnv

    path = (jericho_games / STORY_905["filename"]).resolve()
    monkeypatch.chdir(tmp_path)
    storage = Storage()
    env = FernzEnv(path, seed=SEED_905, save_handler=storage.save, restore_handler=storage.restore)
    reference = FrotzEnv(str(path), seed=SEED_905)
    try:
        actions = reference.get_walkthrough()
        check_step(env, capture_reference(reference, None, plain_text(reference.reset()[0])))
        for action in actions[:11]:
            check_step(
                env, capture_reference(reference, action, plain_text(reference.step(action)[0]))
            )
        if donor == "fernz":
            saved = env.step("save")
            (tmp_path / "905.qzl").write_bytes(storage.data)
            reference.reset()
            restored = reference.step("restore")
            assert window_text(saved[0]) == "\n" + restored[0] + "\n\n>"
        else:
            reference.step("save")
            storage.data = (tmp_path / "905.qzl").read_bytes()
            env.reset()
            assert window_text(env.step("restore")[0]) == "\nOk.\n\n>"
        for action in actions[11:]:
            check_step(
                env, capture_reference(reference, action, plain_text(reference.step(action)[0]))
            )
        assert reference.victory()
    finally:
        env.close()
        reference.close()
