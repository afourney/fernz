"""Issue 58: finite parser work must reach the next input under the default budget."""

from hashlib import sha256
from pathlib import Path

import pytest

from fernz import ExecutionError, FernzEnv

from .observation_helpers import window_text

ROM_SHA256 = "7bffe25e933aa22a2b1e9bfc8073bee5687d79a70394da19e50bfed5755368c4"
# Independently measured using the dfrotz 2.54 executable, seed 1, 100x30.
# Hash only whitespace-normalized lower-window narrative, without its prompt.
OPENING_REPLY = "636604b5b7cf3de4d5cb773a53c3c55e5f8fe2a70c33a955e96d7e412623d6ef"
CAVE_REPLY = "fee35329ed2494223b32076604cdf5afe66e99e89b8d62e66245f4a5f3505053"


def reply_hash(observation):
    narrative = window_text(observation).removesuffix(">")
    return sha256(" ".join(narrative.split()).encode()).hexdigest()


def lostpig(jericho_games):
    path = jericho_games / "lostpig.z8"
    assert sha256(path.read_bytes()).hexdigest() == ROM_SHA256
    return FernzEnv(path, seed=1, screen_width=100, screen_height=30)


@pytest.mark.rom
@pytest.mark.smoke
def test_first_light_torch_exceeds_old_limit_but_completes_by_default(jericho_games):
    env = lostpig(jericho_games)
    env.reset()
    checkpoint = env.get_state()
    with pytest.raises(ExecutionError, match=r"Instruction budget \(250000\) exhausted"):
        env.step("light torch", max_steps=250_000)
    with pytest.raises(RuntimeError, match="reset"):
        env.step("look")
    env.set_state(checkpoint)
    observation, reward, done, info = env.step("light torch")
    assert reply_hash(observation) == OPENING_REPLY
    assert (reward, done, info) == (0, False, {"score": 0, "moves": 1})
    assert env.step("look")[3] == {"score": 0, "moves": 2}


@pytest.mark.rom
def test_original_issue58_route_completes_by_default(jericho_games):
    env = lostpig(jericho_games)
    env.reset()
    route = Path(__file__).with_name("routes").joinpath("lostpig_issue58.txt")
    commands = route.read_text().splitlines()
    assert len(commands) == 38
    for command in commands[:-1]:
        env.step(command)
    assert (env.get_score(), env.get_moves()) == (1, 36)
    observation, reward, done, info = env.step(commands[-1])
    assert reply_hash(observation) == CAVE_REPLY
    assert (reward, done, info) == (0, False, {"score": 1, "moves": 37})
    assert env.step("look")[3] == {"score": 1, "moves": 38}
