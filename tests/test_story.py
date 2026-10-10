from dataclasses import FrozenInstanceError

import pytest

from fernz import Story, StoryFormatError

from .story_files import put_word, story_bytes


@pytest.mark.parametrize("version", range(1, 9))
def test_load_all_versions(version):
    story = Story(story_bytes(version))
    header = story.header
    assert header.version == version
    assert header.release == 42
    assert header.serial == (None if version == 1 else "260101")
    assert header.static_memory == 0x300
    assert header.high_memory == 0x400
    assert header.dictionary == 0x300
    assert header.object_table == 0x40
    assert header.globals_table == 0x100
    assert header.file_length == (4096 if version >= 3 else None)
    assert header.checksum == (0 if version >= 3 else None)
    assert story.verify_checksum() is (True if version >= 3 else None)
    assert story.size == 4096


@pytest.mark.parametrize(
    ("version", "scale"), [(1, 2), (2, 2), (3, 2), (4, 4), (5, 4), (6, 4), (7, 4), (8, 8)]
)
def test_packed_addresses(version, scale):
    data = bytearray(story_bytes(version))
    put_word(data, 0x28, 3)
    put_word(data, 0x2A, 7)
    header = Story(data).header
    routine_offset, string_offset = (24, 56) if version in (6, 7) else (0, 0)
    assert header.routine_offset == routine_offset
    assert header.string_offset == string_offset
    assert header.unpack_routine_address(0x1234) == scale * 0x1234 + routine_offset
    assert header.unpack_string_address(0x1234) == scale * 0x1234 + string_offset
    assert header.unpack_routine_address(0) == routine_offset
    assert header.unpack_string_address(0xFFFF) == scale * 0xFFFF + string_offset


@pytest.mark.parametrize("version", range(1, 9))
def test_only_v6_starts_with_a_packed_routine(version):
    data = bytearray(story_bytes(version))
    put_word(data, 0x06, 0x120)
    put_word(data, 0x28, 0x20)
    header = Story(data).header
    assert header.initial_value == 0x120
    assert header.entry_is_routine is (version == 6)
    assert header.entry_address == (0x580 if version == 6 else 0x120)


@pytest.mark.parametrize("packed", [-1, 65536])
def test_invalid_packed_address(packed):
    header = Story(story_bytes()).header
    with pytest.raises(ValueError, match="16-bit"):
        header.unpack_routine_address(packed)
    with pytest.raises(ValueError, match="16-bit"):
        header.unpack_string_address(packed)


@pytest.mark.parametrize("version", [1, 2])
def test_old_versions_ignore_later_header_fields(version):
    data = bytearray(story_bytes(version))
    for address in (0x1A, 0x1C, 0x28, 0x2A, 0x34, 0x36):
        put_word(data, address, 0xFFFF)
    if version == 1:
        put_word(data, 0x18, 0xFFFF)
    story = Story(data)
    assert story.size == len(data)
    assert story.verify_checksum() is None
    assert story.header.file_length is None
    assert story.header.alphabet_table is None
    assert story.header.extension_table is None
    assert story.header.extension_word(0) == 0
    assert story.header.routine_offset == story.header.string_offset == 0


def test_early_v3_can_omit_length_and_checksum():
    data = bytearray(story_bytes())
    put_word(data, 0x1A, 0)
    put_word(data, 0x1C, 0x1234)
    story = Story(data)
    assert story.header.file_length is None
    assert story.header.checksum is None
    assert story.verify_checksum() is None
    assert story.size == 4096


@pytest.mark.parametrize("version", range(3, 9))
def test_checksum_uses_declared_length_and_excludes_header(version):
    data = bytearray(story_bytes(version))
    data[0x400:0x502] = b"\xff" * 258  # 65790 modulo 65536 = 254.
    put_word(data, 0x1C, 254)
    put_word(data, 0x02, 65535)  # Header changes do not affect the checksum.
    padded = data + b"nonzero padding"
    story = Story(padded)
    assert story.size == 4096
    assert story.data == padded
    assert story.verify_checksum() is True
    data[0x500] ^= 1
    assert Story(data).verify_checksum() is False


def test_zero_checksum_is_verified():
    data = bytearray(story_bytes())
    data[0x500] = 1
    assert Story(data).verify_checksum() is False


@pytest.mark.parametrize("version", range(1, 9))
def test_high_memory_is_not_a_lower_bound_for_entry_or_static_memory(version):
    data = bytearray(story_bytes(version))
    put_word(data, 0x04, 0x200)
    put_word(data, 0x06, 0x20 if version == 6 else 0x80)
    header = Story(data).header
    assert header.entry_address == 0x80
    assert header.entry_address < header.high_memory < header.static_memory


@pytest.mark.parametrize("version", [2, 3, 4, 5, 6, 7, 8])
def test_optional_tables(version):
    data = bytearray(story_bytes(version))
    put_word(data, 0x18, 0x500)
    if version >= 5:
        put_word(data, 0x34, 0x600)
        put_word(data, 0x36, 0x680)
        for offset, value in ((0x680, 3), (0x682, 12), (0x684, 34), (0x686, 0x700)):
            put_word(data, offset, value)
    header = Story(data).header
    assert header.abbreviations_table == 0x500
    if version >= 5:
        assert header.alphabet_table == 0x600
        assert header.extension_table == 0x680
        assert [header.extension_word(i) for i in range(5)] == [3, 12, 34, 0x700, 0]
    else:
        assert header.extension_word(1) == 0
    with pytest.raises(ValueError, match="negative"):
        header.extension_word(-1)


@pytest.mark.parametrize("size", [0, 1, 63])
def test_truncated_header(size):
    with pytest.raises(StoryFormatError, match="64-byte header"):
        Story(b"\x03" * size)


@pytest.mark.parametrize("version", [0, 9, 255])
def test_unsupported_version(version):
    data = bytearray(story_bytes())
    data[0] = version
    with pytest.raises(StoryFormatError, match="Unsupported Z-machine version"):
        Story(data)


def test_container_requires_extraction():
    with pytest.raises(StoryFormatError, match="Blorb"):
        Story(b"FORM" + bytes(100))


@pytest.mark.parametrize("version", range(3, 9))
def test_declared_length_cannot_exceed_available_bytes(version):
    with pytest.raises(StoryFormatError, match="Truncated story"):
        Story(story_bytes(version)[:-1])


@pytest.mark.parametrize("version", range(4, 9))
def test_later_versions_require_file_length(version):
    data = bytearray(story_bytes(version))
    put_word(data, 0x1A, 0)
    with pytest.raises(StoryFormatError, match="nonzero file length"):
        Story(data)


@pytest.mark.parametrize("version", [1, 2, 3])
def test_undeclared_length_still_has_a_version_limit(version):
    data = bytearray(story_bytes(version))
    put_word(data, 0x1A, 0)
    data.extend(bytes(131073 - len(data)))
    with pytest.raises(StoryFormatError, match="size limit"):
        Story(data)


@pytest.mark.parametrize(
    ("version", "size"),
    [
        (1, 131072),
        (2, 131072),
        (3, 131070),
        (4, 262140),
        (5, 262140),
        (6, 524280),
        (7, 524280),
        (8, 524280),
    ],
)
def test_largest_declared_length_and_legacy_limits(version, size):
    story = Story(story_bytes(version, size))
    assert story.size == size
    assert story.verify_checksum() is (None if version <= 2 else True)


def test_v2_abbreviation_table_has_only_32_words():
    data = bytearray(story_bytes(2))
    put_word(data, 0x18, 4096 - 64)
    assert Story(data).header.abbreviations_table == 4032
    data[0] = 3
    with pytest.raises(StoryFormatError, match="Abbreviations table"):
        Story(data)


@pytest.mark.parametrize(("version", "default_bytes"), [(3, 62), (4, 126)])
def test_object_defaults_fit_exactly_in_dynamic_memory(version, default_bytes):
    data = bytearray(story_bytes(version))
    put_word(data, 0x0A, 0x300 - default_bytes)
    assert Story(data).header.object_table == 0x300 - default_bytes
    put_word(data, 0x0A, 0x301 - default_bytes)
    with pytest.raises(StoryFormatError, match="Object defaults"):
        Story(data)


@pytest.mark.parametrize(
    ("address", "value", "message"),
    [
        (0x1A, 1, "smaller than the header"),
        (0x0E, 63, "Static memory"),
        (0x0E, 4097, "Static memory"),
        (0x04, 63, "High memory"),
        (0x04, 4096, "High memory"),
        (0x06, 4096, "Entry point"),
        (0x08, 0, "Dictionary"),
        (0x08, 4096, "Dictionary"),
        (0x0A, 0x2FF, "Object defaults"),
        (0x0C, 0x121, "Globals table"),
        (0x18, 4095, "Abbreviations table"),
        (0x34, 4095, "Alphabet table"),
        (0x36, 4095, "Header extension"),
    ],
)
def test_invalid_header_ranges(address, value, message):
    data = bytearray(story_bytes(5))
    put_word(data, address, value)
    with pytest.raises(StoryFormatError, match=message):
        Story(data)


def test_extension_length_cannot_run_past_memory():
    data = bytearray(story_bytes(5))
    put_word(data, 0x36, 0xFFF - 1)
    put_word(data, 0xFFE, 1)
    with pytest.raises(StoryFormatError, match="Header extension"):
        Story(data)


def test_v6_entry_validation_uses_unpacked_address():
    data = bytearray(story_bytes(6))
    put_word(data, 0x28, 0xFFFF)
    with pytest.raises(StoryFormatError, match="Entry point"):
        Story(data)


def test_story_and_header_are_immutable():
    data = bytearray(story_bytes())
    story = Story(memoryview(data))
    data[0] = 0
    assert story.data[0] == 3
    with pytest.raises(FrozenInstanceError):
        story.header.version = 5
    with pytest.raises(FrozenInstanceError):
        story.data = b""


def test_load_file_ignores_extension_and_preserves_io_errors(tmp_path):
    path = tmp_path / "game.z8"
    path.write_bytes(story_bytes(2))
    assert Story.from_file(path).header.version == 2
    assert Story.from_file(str(path)).data == path.read_bytes()
    with pytest.raises(FileNotFoundError):
        Story.from_file(tmp_path / "missing")
    with pytest.raises(ValueError, match="not a regular file"):
        Story.from_file(tmp_path)
