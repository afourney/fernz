"""Verify the independent vector recorder on authored, non-game fixtures."""

import pytest

from .story_files import put_word, zchars
from .v3_cases import GAMES, selected_games
from .v3_oracle import object_count, object_records, short_name


def test_shards_cover_inventory_once_and_preserve_order():
    groups = [selected_games(f"{i}/3") for i in range(1, 4)]
    assert all(len(group) == 5 for group in groups)
    assert sorted(game for group in groups for game in group) == sorted(GAMES)
    assert len({game for group in groups for game in group}) == 15
    assert selected_games(None) == tuple(GAMES)


@pytest.mark.parametrize("shard", ["0/3", "4/3", "1/16", "1", "foo", "1/0"])
def test_invalid_shards_fail(shard):
    with pytest.raises(ValueError):
        selected_games(shard)


def test_independent_text_decoder_abbreviations_shifts_and_extra_characters():
    data = bytearray(128)
    put_word(data, 0x18, 64)
    put_word(data, 64, 48)  # Abbreviation 0 at byte 96.
    data[96:98] = zchars(6, 7, 8)
    encoded = zchars(1, 0, 0, 4, 6, 5, 6, 4, 27, 5, 7)
    data[32 : 32 + len(encoded)] = encoded
    assert short_name(data, 32, len(encoded) // 2) == "abc Aä\n"
    assert short_name(data, 32, 0) == ""
    with pytest.raises(ValueError, match="Truncated"):
        short_name(bytes(8), 0, None)


def test_independent_object_decoder_keeps_unnamed_nodes_and_long_property_lists():
    data = bytearray(512)
    put_word(data, 0x0A, 64)
    put_word(data, 0x0E, 512)
    # Two entries followed immediately by property tables.
    put_word(data, 133, 144)
    put_word(data, 142, 182)
    data[126] = 0x80
    data[129] = 1
    data[132] = 2
    data[139] = 1
    data[144:147] = b"\x01" + zchars(6, 7, 8)
    data[147:181] = b"".join(bytes((n, n)) for n in range(31, 14, -1))
    assert object_count(data) == 3
    records = object_records(data, 3)
    assert records[1]["name"] == "abc"
    assert records[1]["properties"] == list(range(31, 14, -1))
    assert records[1]["attr"] == [1] + [0] * 30 + [1]
    assert records[1]["child"] == 2
    assert records[2]["name"] == "" and records[2]["parent"] == 1
    assert records[2]["properties"] == [0] * 16
