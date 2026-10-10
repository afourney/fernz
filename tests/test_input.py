import pytest

from fernz import ExecutionError, Memory, Story
from fernz._input import Dictionary, read_line
from fernz._text import Text

from .story_files import READ, program_bytes, zchars


@pytest.mark.parametrize(
    "word,chars",
    [
        (b"i", (14, 5, 5, 5, 5, 5)),
        (b"look", (17, 20, 20, 16, 5, 5)),
        (b"leaflet", (17, 10, 6, 11, 17, 10)),
        (b"1!?", (5, 9, 5, 20, 5, 21)),
        (b"a@b", (6, 5, 6, 2, 0, 7)),
        (b"abcde?", (6, 7, 8, 9, 10, 5)),
        (b"abcd@", (6, 7, 8, 9, 5, 6)),
        (bytes((155,)), (5, 6, 4, 27, 5, 5)),
        (b"", (5, 5, 5, 5, 5, 5)),
    ],
)
def test_dictionary_encoding_matches_specification_zcharacters(word, chars):
    text = Text(Memory(Story(program_bytes(READ))))
    assert text.encode_dictionary(word) == zchars(*chars)


def input_memory(*chunks):
    # Independently specified keys, each followed by opaque game-owned data.
    keys = sorted(
        [
            zchars(5, 19, 5, 5, 5, 5),  # ,
            zchars(11, 14, 24, 13, 14, 19),  # fishin(g)
            zchars(11, 23, 10, 9, 5, 5),  # fred
            zchars(12, 20, 5, 5, 5, 5),  # go
            zchars(17, 10, 6, 11, 17, 10),  # leafle(t)
            zchars(17, 20, 20, 16, 5, 5),  # look
        ]
    )
    dictionary = b'\x03.,"\x07\x00\x06' + b"".join(key + b"\xaa\xbb\xcc" for key in keys)
    return Memory(Story(program_bytes(READ, (0x300, dictionary), *chunks)))


def test_dictionary_binary_search_first_middle_last_and_absent():
    dictionary = Dictionary(input_memory())
    for i, word in enumerate((b",", b"fishing", b"fred", b"go", b"leaflet", b"look")):
        assert dictionary.lookup(word) == 0x307 + 7 * i
    for word in (b"", b"fish", b"gone", b"zzzz"):
        assert dictionary.lookup(word) == 0
    assert dictionary.lookup(b"leaflets") == dictionary.lookup(b"leaflet")


def test_input_splits_separators_preserves_offsets_and_full_word_lengths():
    memory = input_memory((0x280, b"\x1f"), (0x2A0, b"\x06"))
    read_line(memory, 0x280, 0x2A0, " FRED,go  fishing zz")
    assert memory.read_bytes(0x281, 21) == b" fred,go  fishing zz\x00"
    assert memory.read_bytes(0x2A1, 21) == bytes.fromhex(
        "05 03 15 04 02 03 07 01 06 03 1c 02 07 03 0e 07 0b 00 00 02 13"
    )


def test_consecutive_separators_are_individual_words_and_spaces_are_ignored():
    memory = input_memory()
    read_line(memory, 0x280, 0x2A0, ' ,,." ')
    assert memory.read_bytes(0x2A1, 17) == bytes.fromhex(
        "04 03 07 01 02 03 07 01 03 00 00 01 04 00 00 01 05"
    )


def test_parse_limit_leaves_remaining_slots_unchanged():
    memory = input_memory((0x2A0, b"\x02" + b"\xcc" * 17))
    read_line(memory, 0x280, 0x2A0, "look zz go")
    assert memory.read_bytes(0x2A1, 9) == bytes.fromhex("02 03 2a 04 01 00 00 02 06")
    assert memory.read_bytes(0x2AA, 8) == b"\xcc" * 8


@pytest.mark.parametrize("line", ["", "   "])
def test_empty_command_clears_count_without_erasing_unused_records(line):
    memory = input_memory((0x2A0, b"\x04\x03" + b"\xcc" * 16))
    read_line(memory, 0x280, 0x2A0, line)
    assert memory.read_byte(0x2A1) == 0
    assert memory.read_bytes(0x2A2, 16) == b"\xcc" * 16


def test_v3_limit_reserves_space_for_null_and_tokenizes_only_accepted_text():
    memory = input_memory((0x280, b"\x05" + b"\xcc" * 6))
    read_line(memory, 0x280, 0x2A0, "LOOK then")
    assert memory.read_bytes(0x280, 7) == b"\x05look\x00\xcc"
    assert memory.read_bytes(0x2A1, 5) == bytes.fromhex("01 03 2a 04 01")


def test_default_extra_characters_are_lowercased_and_encoded_as_zscii():
    memory = input_memory()
    read_line(memory, 0x280, 0x2A0, "ÄÖÜ É ß")
    assert memory.read_bytes(0x281, 8) == bytes((155, 156, 157, 32, 170, 32, 161, 0))


@pytest.mark.parametrize(
    "line,error",
    [
        (123, TypeError),
        ("a\rb", ValueError),
        ("a\nb", ValueError),
        ("a\x00b", ValueError),
        ("\t", ValueError),
        ("🙂", ValueError),
    ],
)
def test_invalid_input_is_rejected_without_modifying_memory(line, error):
    memory = input_memory()
    before = memory.read_bytes(0, len(memory))
    with pytest.raises(error):
        read_line(memory, 0x280, 0x2A0, line)
    assert memory.read_bytes(0, len(memory)) == before


@pytest.mark.parametrize(
    "text,parse,chunks,match",
    [
        (0x280, 0x2A0, ((0x280, b"\x01"),), "three bytes"),
        (0x280, 0x2A0, ((0x2A0, b"\x00"),), "six bytes"),
        (0x2FD, 0x2A0, ((0x2FD, b"\x14"),), "dynamic memory"),
        (0x280, 0x2FC, ((0x2FC, b"\x04"),), "dynamic memory"),
        (0x280, 0x281, ((0x281, b"\x04"),), "overlap"),
        (0x280, 0x2A0, ((0x304, b"\x03"),), "four bytes"),
        (0x280, 0x2A0, ((0x305, b"\xff\xff"),), "outside byte-addressable"),
        (0x11, 0x2A0, ((0x11, b"\x03"),), "dynamic memory"),
    ],
)
def test_bad_buffers_and_dictionary_fail_before_either_buffer_changes(text, parse, chunks, match):
    memory = input_memory(*chunks)
    before = memory.read_bytes(0, len(memory))
    with pytest.raises(ExecutionError, match=match):
        read_line(memory, text, parse, "look")
    assert memory.read_bytes(0, len(memory)) == before


def test_legacy_parse_capacity_is_checked_against_actual_records_written():
    memory = input_memory((0x2A0, b"\xf0"))
    read_line(memory, 0x280, 0x2A0, "look")
    assert memory.read_bytes(0x2A1, 5) == bytes.fromhex("01 03 2a 04 01")
