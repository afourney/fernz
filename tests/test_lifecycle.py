"""Public input and lifecycle queries need neither snapshots nor private types."""

from dataclasses import replace

import pytest

from fernz import ExecutionError, FernzEnv, Story

from .story_files import READ, program_bytes

CHAR = bytes.fromhex("f6 7f 01 10")


def line_read(version):
    return READ + (b"\x10" if version >= 5 else b"")


def status(env):
    return env.initialized, env.awaiting_character, env.done


@pytest.mark.parametrize("version", (4, 5, 8))
def test_input_modes_enter_space_restore_copy_reset_and_quit(version):
    story = Story(
        program_bytes(
            CHAR + bytes.fromhex("e6 bf 10") + line_read(version) + CHAR + b"\xba", version=version
        )
    )
    env = FernzEnv(story, seed=12)
    assert status(env) == (False, False, False)
    env.reset()
    assert status(env) == (True, True, False)
    character = env.get_state()
    assert env.step(" ")[0].text == "32"
    assert status(env) == (True, False, False)
    line = env.get_state()
    env.set_state(character)
    assert status(env.copy()) == status(env) == (True, True, False)
    assert env.step("")[0].text == "13"
    env.step("look")
    assert status(env) == (True, True, False)
    env.step("x")
    assert status(env) == (True, False, True)
    env.set_state(line)
    assert status(env) == (True, False, False)
    env.reset()
    assert status(env) == (True, True, False)


@pytest.mark.parametrize("version", (3, 4, 5, 8))
def test_failed_execution_and_recovery_are_visible(version):
    env = FernzEnv(
        Story(program_bytes(line_read(version) + b"\xb4\xb4\xba", version=version)), seed=12
    )
    env.reset()
    before = env.get_state()
    with pytest.raises(ExecutionError, match="budget"):
        env.step("look", max_steps=1)
    assert status(env) == (False, False, False)
    env.set_state(before)
    assert status(env) == (True, False, False)
    env.step("look")
    assert status(env) == (True, False, True)
    # Even an invalid reset budget discards the previous execution context.
    with pytest.raises(ValueError, match="positive"):
        env.reset(max_steps=0)
    assert status(env) == (False, False, False)
    env.reset()
    assert status(env) == (True, False, False)
    with pytest.raises(ValueError, match="Program counter"):
        env.set_state(replace(before, pc=-1))
    assert status(env) == (True, False, False)
    assert env.get_state() == before


@pytest.mark.parametrize("character", (False, True))
def test_rejected_actions_and_budgets_preserve_the_episode(character):
    read = CHAR if character else line_read(5)
    env = FernzEnv(Story(program_bytes(read + b"\xba", version=5)), seed=12)
    env.reset()
    before = env.get_state()
    for action, options, error in (
        ("🙂", {}, ValueError),
        ("\n", {}, ValueError),
        (None, {}, TypeError),
        ("x", {"max_steps": 0}, ValueError),
        ("x", {"max_steps": 1.5}, TypeError),
    ):
        with pytest.raises(error):
            env.step(action, **options)
        assert status(env) == (True, character, False)
        assert env.get_state() == before


def test_queries_do_not_snapshot_execute_or_draw_randomness(monkeypatch):
    from fernz._machine import Machine
    from fernz._random import RandomGenerator

    env = FernzEnv(Story(program_bytes(CHAR + b"\xba", version=5)), seed=12)
    env.reset()
    before = env.get_state()

    def unexpected(*args, **kwargs):
        pytest.fail("A lifecycle query must not perform interpreter work")

    with monkeypatch.context() as patch:
        patch.setattr(FernzEnv, "get_state", unexpected)
        patch.setattr(Machine, "run", unexpected)
        patch.setattr(RandomGenerator, "random", unexpected)
        patch.setattr(RandomGenerator, "reset", unexpected)
        for _ in range(3):
            assert status(env) == (True, True, False)
    assert env.get_state() == before


def test_callback_value_error_invalidates_execution():
    def failed_save(data):
        raise ValueError("Host callback failed")

    env = FernzEnv(Story(program_bytes(READ + b"\xb5\xc2" + READ)), save_handler=failed_save)
    env.reset()
    with pytest.raises(ValueError, match="Host callback"):
        env.step("save")
    assert status(env) == (False, False, False)


@pytest.mark.parametrize("version", (4, 5, 8))
def test_failure_after_character_input_clears_both_queries(version):
    env = FernzEnv(Story(program_bytes(CHAR + b"\xb4\xb4\xba", version=version)))
    env.reset()
    with pytest.raises(ExecutionError):
        env.step(" ", max_steps=1)
    assert status(env) == (False, False, False)


def test_failed_opening_never_initializes_an_environment():
    env = FernzEnv(Story(program_bytes(bytes.fromhex("8c ff ff"))))
    with pytest.raises(ExecutionError, match="budget"):
        env.reset(max_steps=3)
    assert status(env) == (False, False, False)


@pytest.mark.parametrize("version", (3, 4, 5, 8))
def test_fatal_input_buffer_error_invalidates_execution(version):
    env = FernzEnv(Story(program_bytes(line_read(version), version=version)))
    env.reset()
    env.memory.write_byte(0x280, 0)
    with pytest.raises(ExecutionError, match="text buffer"):
        env.step("look")
    assert status(env) == (False, False, False)
