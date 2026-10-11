"""V4 SAVE probes assembled independently from Standard 1.1 §§6, 14, 15."""

from .story_files import READ, program_bytes


def save_story(*, store=8, high=False):
    address = 0x10000 if high else 0x600
    # Call with seven arguments; unlike V5, all eight initial locals follow
    # the count byte. The call stores its return value in global 17.
    root = bytes.fromhex("ec 15 55") + (address // 4).to_bytes(2, "big")
    root += bytes((1, 2, 3, 4, 5, 6, 7, 17))
    root += bytes.fromhex("e6 bf 11 bb") + READ + b"\xba"
    routine = b"\x08" + b"\x00\x63" * 8
    routine += bytes.fromhex("e8 3f 22 22") + READ
    # Restore if the command starts with r, otherwise save. Both are 0OP
    # instructions with a store byte; neither has a branch or EXT prefix.
    routine += bytes.fromhex("d0 1f 02 80 01 08 41 08 72 c7")
    routine += bytes((0xB5, store)) + bytes.fromhex("8c 00 04")
    routine += bytes((0xB6, store, 0xE6, 0xBF, store, 0xBB))
    routine += READ + bytes.fromhex("e6 bf 00 bb ab 07")
    return program_bytes(
        root,
        (address, routine),
        (0xCA, b"\x00\xcc"),
        version=4,
        size=address + 0x4000 if high else 4096,
    )
