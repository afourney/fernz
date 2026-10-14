"""Environment construction from immutable story images, with no file coupling."""

import pytest

from fernz import FernzEnv, Story

from .story_files import READ, program_bytes, story_bytes


@pytest.mark.parametrize("version", (1, 2, 3, 4, 5, 6, 7, 8))
def test_story_construction_loads_without_executing_or_reopening(tmp_path, monkeypatch, version):
    from fernz._machine import Machine
    from fernz._random import RandomGenerator

    path = tmp_path / "story"
    path.write_bytes(story_bytes(version))
    story = Story.from_file(path)
    path.unlink()

    def unexpected(*args, **kwargs):
        pytest.fail("Construction must not reopen a file, execute, or initialize an RNG")

    monkeypatch.setattr(Story, "from_file", unexpected)
    monkeypatch.setattr(Machine, "run", unexpected)
    monkeypatch.setattr(RandomGenerator, "__init__", unexpected)
    first = FernzEnv(story, screen_width=43, screen_height=17)
    second = FernzEnv(story, seed=42)
    assert first.story is second.story is story
    assert first.game_path is second.game_path is None
    assert not first.initialized and not second.initialized
    assert (first.screen_width, first.screen_height) == (43, 17)
    first.memory.write_byte(0x100, 42)
    assert second.memory.read_byte(0x100) == story.data[0x100] == 0
    assert first.copy().game_path is None


@pytest.mark.parametrize("version", (3, 4, 5, 8))
def test_restore_candidate_is_independent_and_does_not_execute(monkeypatch, version):
    from fernz._machine import Machine

    read = READ + (b"\x10" if version >= 5 else b"")
    story = Story(
        program_bytes(read + bytes.fromhex("e7 3f 7f ff 11 e6 bf 11") + read, version=version)
    )
    original = FernzEnv(story, seed=12, screen_width=43, screen_height=17)
    original.reset()
    state = original.get_state()

    def unexpected(*args, **kwargs):
        pytest.fail("Restoring a candidate must not execute the opening")

    with monkeypatch.context() as patch:
        patch.setattr(Machine, "run", unexpected)
        candidate = FernzEnv(story, seed=99)
        candidate.set_state(state)
    assert candidate.get_state() == state
    assert (candidate.screen_width, candidate.screen_height) == (43, 17)
    result = candidate.step("look")
    assert original.get_state() == state
    assert original.step("look") == result
    candidate.memory.write_byte(0x250, 7)
    assert original.memory.read_byte(0x250) == 0


@pytest.mark.parametrize(
    "options, error",
    [
        ({"seed": -1}, ValueError),
        ({"screen_width": 0}, ValueError),
        ({"screen_height": 255}, ValueError),
        ({"screen_width": True}, TypeError),
        ({"save_handler": 1}, TypeError),
        ({"restore_handler": False}, TypeError),
    ],
)
def test_story_constructor_validates_the_same_options(options, error):
    with pytest.raises(error):
        FernzEnv(Story(story_bytes()), **options)
