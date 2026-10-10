import pytest

from fernz import ExecutionError, Memory, MemoryAccessError, Story
from fernz._text import Text, zscii

from .story_files import program_bytes, put_word, zchars


def text_memory(data):
    return Memory(Story(program_bytes(b"\xba", (0x600, data))))


def test_specification_hello_example():
    assert Text(text_memory(bytes.fromhex("11 aa 46 34 16 45 9c a5"))).decode(0x600) == "Hello.\n"


@pytest.mark.parametrize(
    "chars,expected",
    [
        ((6, 7, 8), "abc"),
        ((4, 6, 6), "Aa"),
        ((5, 5, 7), "\n"),
        ((4, 0, 6), " a"),
        ((5, 6, 2, 0, 6), "@a"),
        ((5, 6, 0, 0, 6), "a"),
        ((5, 6, 4, 27), "ä"),
        ((6, 5, 6), "a"),
        ((6, 7, 1), "ab"),
        ((6, 7, 5), "ab"),
    ],
)
def test_shifts_escapes_spaces_and_incomplete_constructions(chars, expected):
    assert Text(text_memory(zchars(*chars))).decode(0x600) == expected


@pytest.mark.parametrize("bank", (1, 2, 3))
def test_abbreviations_use_word_addresses_and_reset_alphabet(bank):
    data = bytearray(program_bytes(b"\xba", (0x600, zchars(4, bank, 7, 6)), (0x700, zchars(7, 8))))
    put_word(data, 0x18, 0x300)
    put_word(data, 0x300 + 2 * (32 * (bank - 1) + 7), 0x380)
    assert Text(Memory(Story(data))).decode(0x600) == "bca"


def test_nested_abbreviation_rejected_without_recursion():
    data = bytearray(program_bytes(b"\xba", (0x600, zchars(1, 0)), (0x700, zchars(1, 0))))
    put_word(data, 0x18, 0x300)
    put_word(data, 0x300, 0x380)
    with pytest.raises(ExecutionError, match="cannot contain"):
        Text(Memory(Story(data))).decode(0x600)


def test_missing_abbreviation_table():
    with pytest.raises(ExecutionError, match="without a table"):
        Text(text_memory(zchars(1, 0))).decode(0x600)


def test_truncated_string_and_object_name_boundary():
    text = Text(text_memory(b"\x00\x00"))
    with pytest.raises(MemoryAccessError):
        text.decode(0x600)
    with pytest.raises(ExecutionError, match="Unterminated object name"):
        text.decode(0x600, words=1)
    assert text.decode(0x600, words=0) == ""


def test_abbreviation_cannot_end_mid_escape():
    with pytest.raises(ExecutionError, match="Incomplete"):
        Text(text_memory(zchars(6, 5, 6))).decode(0x600, abbreviation=True)


@pytest.mark.parametrize(
    "code,expected",
    [(0, ""), (13, "\n"), (32, " "), (126, "~"), (155, "ä"), (180, "Ý"), (220, "œ"), (223, "¿")],
)
def test_zscii(code, expected):
    assert zscii(code) == expected


@pytest.mark.parametrize("code", (-1, 1, 9, 11, 127, 129, 224, 255, 1023))
def test_undefined_or_input_only_zscii(code):
    with pytest.raises(ExecutionError, match="Invalid V3 output"):
        zscii(code)


def test_text_reads_live_memory():
    memory = Memory(Story(program_bytes(b"\xba", (0x240, zchars(6, 7, 8)))))
    text = Text(memory)
    assert text.decode(0x240) == "abc"
    memory.write_bytes(0x240, zchars(9, 10, 11))
    assert text.decode(0x240) == "def"
