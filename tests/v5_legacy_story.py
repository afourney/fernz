"""Independent programs isolating historical V5 object operations."""

from .save_story import number
from .test_v5_foundations import object_memory


def legacy_story(code, *, duplicate=False):
    data = bytearray(object_memory().story.data)
    if duplicate:
        table = int.from_bytes(data[0xCA:0xCC], "big")
        data[table : table + 11] = bytes.fromhex("00 49 00 0b 49 00 16 48 00 21 00")
    data[0x2100 : 0x2100 + len(code)] = code
    return bytes(data)


def duplicate_story():
    code = bytes.fromhex("11 01 09 11") + number(17)
    code += bytes.fromhex("13 01 09 11") + number(17)
    code += bytes.fromhex("11 01 08 11") + number(17)
    code += bytes.fromhex("e3 57 01 09 63 11 01 09 11") + number(17)
    return legacy_story(code + b"\xba", duplicate=True)


def zero_story(source, destination):
    # Place 1 inside 2 first, so a mistaken removal is observable.
    code = bytes.fromhex("0e 01 02") + bytes((0x0E, source, destination))
    code += bytes.fromhex("93 01 11") + number(17)
    code += bytes.fromhex("92 02 11 c2") + number(17)
    return legacy_story(code + b"\xba")


def long_property_story(size):
    data = bytearray(legacy_story(bytes.fromhex("11 01 01 11") + number(17) + b"\xba"))
    table = int.from_bytes(data[0xCA:0xCC], "big")
    data[table : table + size + 4] = (
        bytes((0, 0x81, 0x80 | (size & 63))) + b"\x12\x34" + bytes(size - 2) + b"\0"
    )
    return bytes(data)
