"""Loading coverage for every retained ROM, without importing an interpreter."""

import pytest

from fernz import FernzEnv, Memory, MemoryAccessError, Story

pytestmark = pytest.mark.rom

# Explicit cases keep each game's result visible and stable in CI. Versions
# were read from the retained corpus headers, not inferred from filenames.
GAMES = {
    3: (
        "ballyhoo.z3",
        "cutthroat.z3",
        "enchanter.z3",
        "hhgg.z3",
        "hollywood.z3",
        "infidel.z3",
        "lurking.z3",
        "planetfall.z3",
        "plundered.z3",
        "seastalker.z3",
        "sorcerer.z3",
        "spellbrkr.z3",
        "wishbringer.z3",
        "zork1.z5",
        "zork2.z5",
        "zork3.z5",
    ),
    4: ("trinity.z4",),
    5: (
        "905.z5",
        "acorncourt.z5",
        "advent.z5",
        "adventureland.z5",
        "awaken.z5",
        "balances.z5",
        "curses.z5",
        "deephome.z5",
        "detective.z5",
        "dragon.z5",
        "enter.z5",
        "gold.z5",
        "huntdark.z5",
        "inhumane.z5",
        "jewel.z5",
        "karn.z5",
        "library.z5",
        "loose.z5",
        "ludicorp.z5",
        "moonlit.z5",
        "murdac.z5",
        "night.z5",
        "omniquest.z5",
        "pentari.z5",
        "reverb.z5",
        "sherlock.z5",
        "spirit.z5",
        "temple.z5",
        "theatre.z5",
        "tryst205.z5",
        "weapon.z5",
        "zenon.z5",
        "ztuu.z5",
    ),
    8: (
        "afflicted.z8",
        "anchor.z8",
        "lostpig.z8",
        "partyfoul.z8",
        "snacktime.z8",
        "yomomma.z8",
    ),
}


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
