import pytest

from fernz import Memory, MemoryAccessError, Story

from .story_files import put_word, story_bytes


@pytest.mark.parametrize("version", range(1, 9))
def test_unsigned_big_endian_access_and_independent_instances(version):
    story = Story(story_bytes(version))
    memory, other = Memory(story), Memory(story)
    memory.write_word(0x101, 0xFEDC)  # Odd byte addresses are legal.
    memory.write_byte(0x103, 255)
    assert memory.read_bytes(0x101, 3) == b"\xfe\xdc\xff"
    assert memory.read_word(0x101) == 0xFEDC
    assert memory.read_byte(0x102) == 0xDC
    assert other.read_word(0x101) == 0
    assert story.data[0x101:0x103] == b"\x00\x00"
    assert story.verify_checksum() is (True if version >= 3 else None)


def test_reads_can_cross_regions_and_access_high_memory():
    data = bytearray(story_bytes(8, size=0x20000))
    data[0x2FF:0x301] = b"\x12\x34"
    data[0x1FFFE:] = b"\xab\xcd"
    memory = Memory(Story(data))
    assert memory.read_word(0x2FF) == 0x1234
    assert memory.read_word(0x1FFFE) == 0xABCD
    assert memory.read_byte(0x1FFFF) == 0xCD


@pytest.mark.parametrize(("address", "length"), [(-1, 1), (0, -1), (4096, 1), (4095, 2), (4097, 0)])
def test_read_bounds(address, length):
    memory = Memory(Story(story_bytes()))
    with pytest.raises(MemoryAccessError, match="outside memory"):
        memory.read_bytes(address, length)


def test_word_and_byte_reads_do_not_wrap_or_truncate():
    memory = Memory(Story(story_bytes()))
    for address in (-1, len(memory)):
        with pytest.raises(MemoryAccessError):
            memory.read_byte(address)
    with pytest.raises(MemoryAccessError):
        memory.read_word(len(memory) - 1)


@pytest.mark.parametrize("address", [-1, 0x300, 0x400, 4096])
def test_writes_cannot_reach_static_high_or_out_of_bounds_memory(address):
    memory = Memory(Story(story_bytes()))
    original = memory.read_bytes(0, len(memory))
    with pytest.raises(MemoryAccessError):
        memory.write_byte(address, 1)
    assert memory.read_bytes(0, len(memory)) == original


def test_word_crossing_static_boundary_is_atomic():
    memory = Memory(Story(story_bytes()))
    memory.write_byte(0x2FF, 0xAB)
    with pytest.raises(MemoryAccessError, match="read-only"):
        memory.write_word(0x2FF, 0x1234)
    assert memory.read_word(0x2FF) == 0xAB00


@pytest.mark.parametrize("version", range(1, 9))
def test_header_game_writable_bits(version):
    memory = Memory(Story(story_bytes(version)))
    allowed = 1 if version <= 2 else 3
    memory.write_word(0x10, allowed)
    assert memory.read_word(0x10) == allowed
    assert memory.story.header.flags2 == 0  # Initial metadata is a snapshot.
    with pytest.raises(MemoryAccessError, match="protected header"):
        memory.write_word(0x10, 0x100 | allowed)
    with pytest.raises(MemoryAccessError, match="protected header"):
        memory.write_byte(0x11, 0x04 | allowed)
    assert memory.read_word(0x10) == allowed
    memory.write_word(0x10, 0)


def test_v6_can_clear_but_not_set_a_redraw_request():
    data = bytearray(story_bytes(6))
    data[0x11] = 4
    memory = Memory(Story(data))
    memory.write_byte(0x11, 3)
    assert memory.read_word(0x10) == 3
    with pytest.raises(MemoryAccessError):
        memory.write_byte(0x11, 7)


@pytest.mark.parametrize("address", [0, 1, 2, 4, 6, 8, 10, 12, 14, 0x1A, 0x1C, 0x32, 0x3F])
def test_protected_header_fields(address):
    memory = Memory(Story(story_bytes()))
    value = memory.read_byte(address)
    memory.write_byte(address, value)  # An unchanged bit is not altered.
    with pytest.raises(MemoryAccessError, match="protected header"):
        memory.write_byte(address, value ^ 1)


def test_header_write_is_atomic():
    memory = Memory(Story(story_bytes()))
    original = memory.read_word(0x11)
    with pytest.raises(MemoryAccessError, match="protected header"):
        memory.write_word(0x11, 0x0100)
    assert memory.read_word(0x11) == original


def test_header_extension_is_protected_even_in_dynamic_memory():
    data = bytearray(story_bytes(5))
    put_word(data, 0x36, 0x2E0)
    put_word(data, 0x2E0, 1)
    put_word(data, 0x2E2, 42)
    memory = Memory(Story(data))
    with pytest.raises(MemoryAccessError, match="protected header"):
        memory.write_word(0x2E2, 43)
    with pytest.raises(MemoryAccessError, match="protected header"):
        memory.write_bytes(0x2DF, b"\x01\xff")
    assert memory.read_byte(0x2DF) == 0
    assert memory.read_word(0x2E2) == 42
    memory.write_byte(0x2E4, 1)  # The protection ends with the actual table.


def test_high_memory_marker_does_not_shrink_dynamic_memory():
    data = bytearray(story_bytes())
    put_word(data, 4, 0x200)
    memory = Memory(Story(data))
    memory.write_byte(0x2FF, 42)
    assert memory.read_byte(0x2FF) == 42


@pytest.mark.parametrize(
    ("method", "value"),
    [("write_byte", -1), ("write_byte", 256), ("write_word", -1), ("write_word", 65536)],
)
def test_write_values_do_not_silently_wrap(method, value):
    memory = Memory(Story(story_bytes()))
    with pytest.raises(ValueError, match="unsigned"):
        getattr(memory, method)(0x100, value)
    assert memory.read_word(0x100) == 0


def test_reset_and_copy_preserve_independence_and_original_checksum():
    story = Story(story_bytes())
    memory = Memory(story)
    memory.write_word(0x100, 0xCAFE)
    memory.write_byte(0x11, 3)
    copied = memory.copy()
    assert copied.story is story
    assert copied.read_word(0x100) == 0xCAFE
    memory.reset()
    assert memory.read_bytes(0, len(memory)) == story.data
    assert copied.read_byte(0x11) == 3
    copied.write_word(0x100, 0xBEEF)
    assert memory.read_word(0x100) == 0
    copied.reset()
    assert copied.read_bytes(0, len(copied)) == story.data
    assert story.verify_checksum() is True


def test_padding_is_not_addressable_and_empty_accesses_are_defined():
    story = Story(story_bytes() + b"padding")
    memory = Memory(story)
    assert len(memory) == 4096
    assert memory.read_bytes(4096, 0) == b""
    memory.write_bytes(4096, b"")
    with pytest.raises(MemoryAccessError):
        memory.read_byte(4096)


def test_byte_buffers_are_copied():
    memory = Memory(Story(story_bytes()))
    source = bytearray(b"\xab\xcd")
    memory.write_bytes(0x100, source)
    source[0] = 0
    result = memory.read_bytes(0x100, 2)
    assert isinstance(result, bytes)
    assert result == b"\xab\xcd"
