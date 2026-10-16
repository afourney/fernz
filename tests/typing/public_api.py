"""Static consumer examples, checked by Pyright without executing a story."""

from typing import assert_type

from fernz import (
    ColourPair,
    Cursor,
    FernzEnv,
    GameState,
    MemoryStream,
    Observation,
    PythonRandomState,
    ResetResult,
    StatusInfo,
    StepResult,
)


def public_results(env: FernzEnv) -> None:
    reset: ResetResult = env.reset()
    observation, info = reset
    assert_type(observation, Observation)
    assert_type(info, StatusInfo)
    # Preserve the existing mutable dict[str, object] API for consumers.
    metadata: dict[str, object] = info
    metadata["consumer_tag"] = "example"
    step: StepResult = env.step("look")
    assert_type(step[0], Observation)
    assert_type(step[1], int)
    assert_type(step[2], bool)
    assert_type(step[3], StatusInfo)


def checkpoint_fields(state: GameState) -> None:
    assert_type(state.output.cursors[0], Cursor)
    assert_type(state.output.colours[0], ColourPair)
    assert_type(state.output.memory_streams[0], MemoryStream)
    assert_type(state.rng.python_state, PythonRandomState | None)
