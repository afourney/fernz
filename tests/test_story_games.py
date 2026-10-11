"""Loading coverage for every retained ROM, without importing an interpreter."""

import json
from dataclasses import fields

import pytest

from fernz import FernzEnv, Memory, MemoryAccessError, Story, _cli

from .story_corpus import GAMES
from .vector_archive import STORYFILES_PATH, digest, read_archive

pytestmark = [pytest.mark.rom, pytest.mark.smoke]


@pytest.fixture(scope="module")
def story_vectors():
    documents = read_archive(STORYFILES_PATH)
    manifest = documents["manifest.json"]
    filenames = {name for names in GAMES.values() for name in names}
    assert manifest["kind"] == "storyfiles"
    assert manifest["story_count"] == len(filenames) == 56
    assert set(documents) == {"manifest.json", *(name + ".json" for name in filenames)}
    return documents


@pytest.mark.parametrize(
    ("filename", "version"), [(name, version) for version, names in GAMES.items() for name in names]
)
def test_load_retained_story(jericho_games, filename, version):
    story = Story.from_file(jericho_games / filename)
    assert story.header.version == version
    assert story.verify_checksum() is True
    memory = Memory(story)
    assert len(memory) == story.size
    assert memory.read_byte(0) == version
    original = memory.read_word(story.header.globals_table)
    memory.write_word(story.header.globals_table, original ^ 0xFFFF)
    assert Memory(story).read_word(story.header.globals_table) == original
    with pytest.raises(MemoryAccessError, match="read-only"):
        memory.write_byte(story.header.static_memory, 0)
    memory.reset()
    assert memory.read_word(story.header.globals_table) == original
    assert story.verify_checksum() is True


@pytest.mark.vectors
@pytest.mark.parametrize(
    ("filename", "version"), [(name, version) for version, names in GAMES.items() for name in names]
)
def test_retained_story_vector(jericho_games, story_vectors, filename, version):
    expected = story_vectors[filename + ".json"]
    story = Story.from_file(jericho_games / filename)
    header = story.header
    assert digest(story.data) == expected["file_sha256"], f"Unexpected ROM bytes: {filename}"
    assert len(story.data) == expected["file_size"]
    assert story.size == expected["story_size"]
    assert header.version == expected["header"]["version"] == version
    public_fields = {field.name for field in fields(header) if not field.name.startswith("_")}
    assert public_fields == expected["header"].keys()
    for name, value in expected["header"].items():
        assert getattr(header, name) == value, name
    for name in ("entry_address", "entry_is_routine", "packed_address_scale"):
        assert getattr(header, name) == expected[name], name
    extension_words = expected["extension_words"]
    assert [header.extension_word(i) for i in range(len(extension_words))] == extension_words
    assert header.extension_word(len(extension_words)) == 0
    assert story.verify_checksum() is expected["checksum_valid"] is True
    assert header.checksum == expected["calculated_checksum"]
    memory = Memory(story)
    assert len(memory) == expected["story_size"]
    assert memory.read_byte(0) == version
    assert digest(memory.read_bytes(0, len(memory))) == expected["memory_sha256"]
    assert digest(memory.read_bytes(0, header.static_memory)) == expected["dynamic_sha256"]
    assert (
        digest(memory.read_bytes(header.static_memory, len(memory) - header.static_memory))
        == expected["static_sha256"]
    )
    assert digest(memory.read_bytes(header.globals_table, 480)) == expected["globals_sha256"]
    original = memory.read_word(header.globals_table)
    assert original == expected["first_global"]
    memory.write_word(header.globals_table, original ^ 0xFFFF)
    assert memory.read_word(header.globals_table) == original ^ 0xFFFF
    assert Memory(story).read_word(header.globals_table) == original
    copy = memory.copy()
    assert copy.read_word(header.globals_table) == original ^ 0xFFFF
    copy.reset()
    assert digest(copy.read_bytes(0, len(copy))) == expected["memory_sha256"]
    assert memory.read_word(header.globals_table) == original ^ 0xFFFF
    with pytest.raises(MemoryAccessError, match="read-only"):
        memory.write_byte(header.static_memory, 0)
    with pytest.raises(MemoryAccessError, match="outside memory"):
        memory.read_byte(expected["story_size"])
    memory.reset()
    assert digest(memory.read_bytes(0, len(memory))) == expected["memory_sha256"]
    assert digest(story.data) == expected["file_sha256"]
    assert story.verify_checksum() is True


@pytest.mark.vectors
@pytest.mark.parametrize("filename", [name for names in GAMES.values() for name in names])
def test_retained_story_info(jericho_games, story_vectors, filename, capsys):
    expected = story_vectors[filename + ".json"]
    env = FernzEnv(jericho_games / filename)
    try:
        assert digest(env.story.data) == expected["file_sha256"]
        assert len(env.memory) == expected["story_size"]
        assert digest(env.memory.read_bytes(0, len(env.memory))) == expected["memory_sha256"]
    finally:
        env.close()
    # --inspect loads metadata through the environment without executing the
    # game; this is supported for all retained versions, not just V3.
    assert _cli.main(["--inspect", str(jericho_games / filename)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        **{
            name: expected["header"][name]
            for name in ("version", "release", "serial", "static_memory", "high_memory")
        },
        **{
            name: expected[name]
            for name in ("file_size", "story_size", "entry_address", "checksum_valid")
        },
        "entry_kind": "routine" if expected["entry_is_routine"] else "instruction",
    }


def test_zork1_metadata_through_environment(jericho_games):
    env = FernzEnv(jericho_games / "zork1.z5")
    try:
        header = env.story.header
        assert header.version == 3
        assert header.release == 88
        assert header.serial == "840726"
        assert header.entry_address == 0x4F05
        assert header.static_memory == 0x2E53
        assert header.high_memory == 0x4E37
        assert len(env.story.data) == 92160
        assert len(env.memory) == env.story.size == 84876
        assert env.story.verify_checksum() is True
    finally:
        env.close()


def test_zork1_runs_to_first_prompt_and_resets(jericho_games):
    env = FernzEnv(jericho_games / "zork1.z5", seed=0)
    try:
        initial = env.reset()
        observation, info = initial
        assert observation.startswith("ZORK I:")
        assert "West of House\n" in observation
        assert observation.endswith("\n\n>")
        assert info == {"score": 0, "moves": 0}
        assert env._machine.input_request is not None
        assert env._machine.halted is False
        env.memory.write_word(env.story.header.globals_table + 2, 17)
        assert env.reset() == initial
    finally:
        env.close()


def test_zork1_mailbox_leaflet_and_quit(jericho_games):
    env = FernzEnv(jericho_games / "zork1.z5", seed=42)
    try:
        for _ in range(2):
            env.reset()
            for move, (action, text) in enumerate(
                (
                    ("look", "West of House"),
                    ("open mailbox", "Opening the small mailbox reveals a leaflet."),
                    ("take leaflet", "Taken."),
                    ("read leaflet", '"WELCOME TO ZORK!'),
                    ("inventory", "You are carrying:\n  A leaflet"),
                ),
                start=1,
            ):
                observation, reward, done, info = env.step(action)
                assert text in observation
                assert observation.startswith("\n")
                assert observation.endswith("\n>")
                assert reward == 0
                assert done is False
                assert info == {"score": 0, "moves": move}
            assert "Do you wish to leave" in env.step("quit")[0]
            assert env.step("yes")[2] is True
    finally:
        env.close()
