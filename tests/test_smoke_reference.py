"""Short live comparisons through documented public APIs, without full routes."""

import pytest

from fernz import FernzEnv

from .v3_cases import GAMES
from .v3_reference import Reference
from .v3_vectors import step_and_check

pytestmark = [pytest.mark.reference, pytest.mark.smoke]


def test_opening_and_five_commands_match_live_reference(v3_game, jericho_games):
    game = v3_game
    path = jericho_games / GAMES[game]["filename"]
    reference = Reference(path, game)
    env = FernzEnv(path, seed=reference.seed)
    try:
        step_and_check(env, reference.opening(), game)
        actions = reference.env.get_walkthrough()[:5]
        assert len(actions) == 5
        for action in actions:
            step_and_check(env, reference.step(action), game)
    finally:
        env.close()
        reference.close()
