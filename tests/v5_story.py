"""Hand-assembled V5 save probes, independent of compilers or interpreters."""

from .story_files import READ, program_bytes


def save_story(*, store=8, high=False):
    address = 0x10000 if high else 0x600
    packed = address // 4
    clear = bytes.fromhex("e2 17 02 80 01 00")
    read = clear + READ + b"\x08"  # Result local 8 inside the callee.
    root = bytes.fromhex("0d 11 4d fa 15 55") + packed.to_bytes(2, "big")
    root += bytes((1, 2, 3, 4, 5, 6, 7))
    root += bytes.fromhex("e6 bf 11 bb") + clear + READ + b"\x10\xba"
    routine = b"\x08" + bytes.fromhex("e8 3f 22 22") + read
    routine += bytes.fromhex("d0 1f 02 80 02 08 41 08 72 c9")
    routine += bytes((0xBE, 0, 0xFF, store)) + bytes.fromhex("8c 00 06")
    routine += bytes((0xBE, 1, 0xFF, store, 0xE6, 0xBF, store, 0xBB))
    routine += read + bytes.fromhex("e6 bf 00 bb ab 01")
    return program_bytes(
        root,
        (address, routine),
        (0xCA, b"\x00\xcc"),
        version=5,
        size=0x14000 if high else 4096,
    )
