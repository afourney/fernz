"""Full Balances and Sherlock comparisons through the documented reference API."""

import pytest

from .scripts.v5_trajectory_vectors import generate_trajectory
from .v5_trajectory_cases import GAMES
from .v5_trajectory_vectors import replay_trajectory

pytestmark = [pytest.mark.reference, pytest.mark.v5games]


@pytest.mark.parametrize("game", GAMES)
def test_v5_full_trajectory_live(jericho_games, game):
    path = jericho_games / f"{game}.z5"
    replay_trajectory(path, game, generate_trajectory(path, game))


@pytest.mark.parametrize("game", GAMES)
@pytest.mark.parametrize("value", (0, 255, 256, 32767, 32768, 65535))
def test_profile_counters_use_measured_public_ram_fields(jericho_games, game, value):
    from dataclasses import replace

    from jericho import FrotzEnv

    from fernz import FernzEnv

    from .v5_corpus_vectors import reset_fernz

    path = jericho_games / f"{game}.z5"
    reference = FrotzEnv(str(path), seed=0)
    env = FernzEnv(path, seed=0)
    try:
        reference.reset()
        reset_fernz(env, game)
        native, state = reference.get_state(), env.get_state()
        ram, actual = native[0].copy(), bytearray(state.ram)
        base = int.from_bytes(actual[12:14], "big")
        for field in ("score_global", "moves_global"):
            address = base + 2 * GAMES[game][field]
            ram[address : address + 2] = list(value.to_bytes(2, "big"))
            actual[address : address + 2] = value.to_bytes(2, "big")
        reference.set_state((ram, *native[1:]))
        env.set_state(replace(state, ram=bytes(actual)))
        assert env.get_score() == reference.get_score() == value & 255
        assert env.get_moves() == reference.get_moves() == value
    finally:
        reference.close()
        env.close()


@pytest.mark.parametrize("game", GAMES)
@pytest.mark.parametrize("donor", ("fernz", "jericho"))
def test_midgame_quetzal_interchange_continues_to_victory(
    jericho_games, tmp_path, monkeypatch, game, donor
):
    from dataclasses import replace

    from jericho import FrotzEnv

    from fernz import FernzEnv

    from .test_save_restore import Storage
    from .v5_corpus_vectors import reset_fernz
    from .v5_trajectory_cases import PERSISTENCE_TURN
    from .v5_trajectory_vectors import capture, check_step

    path = (jericho_games / f"{game}.z5").resolve()
    original = path.read_bytes()
    monkeypatch.chdir(tmp_path)
    storage = Storage()
    env = FernzEnv(path, seed=0, save_handler=storage.save, restore_handler=storage.restore)
    reference = FrotzEnv(str(path), seed=0)
    try:
        opening, info = reference.reset()
        check_step(env, game, capture(reference, original, game, None, (opening, 0, False, info)))
        actions = reference.get_walkthrough()
        turn = PERSISTENCE_TURN[game]
        for action in actions[:turn]:
            check_step(
                env, game, capture(reference, original, game, action, reference.step(action))
            )
        before, native_before = env.get_state(), reference.get_state()
        if donor == "fernz":
            env.step("save")
            assert storage.data is not None
            (tmp_path / f"{game}.qzl").write_bytes(storage.data)
            reference.reset()
            current = reference.get_state()
            # Quetzal deliberately excludes RNG. Preserve the recipient's
            # controlled live sequence separately through the public snapshot.
            reference.set_state((*current[:7], native_before[7], *current[8:]))
            reference.step("restore")
            env.step("restore")
        else:
            reference.step("save")
            storage.data = (tmp_path / f"{game}.qzl").read_bytes()
            reset_fernz(env, game)
            env.set_state(replace(env.get_state(), rng=before.rng))
            env.step("restore")
            reference.step("restore")
        for action in actions[turn:]:
            check_step(
                env, game, capture(reference, original, game, action, reference.step(action))
            )
        assert env.victory() and reference.victory()
        assert env.get_score() == GAMES[game]["winning_score"]
    finally:
        env.close()
        reference.close()
