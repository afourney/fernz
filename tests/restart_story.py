"""Independent V3 restart probe assembled from the opcode specification."""

from .save_story import call, number
from .story_files import READ, program_bytes


def restart_story(*, opcode_seed=5, flags2=2):
    """Enter two routines, mutate memory and RNG, pause, then restart.

    Startup prints the host-seeded first draw. Restart prints a marker before
    returning to startup, where every stack and input buffer should be fresh.
    """
    root = bytes.fromhex("e7 3f 7f ff 13") + number(19) + READ
    root += bytes.fromhex("e8 3f 11 11") + call(0x600, (7,), 20) + b"\x00"
    outer = bytes.fromhex("02 00 11 00 12 e8 3f 22 22")
    outer += call(0x800, (7, 8, 9), 1) + b"\x00"
    inner = bytes.fromhex("03 44 44 55 55 66 66 e8 3f 33 33")
    inner += bytes.fromhex("0d 11 49 0d 12 63 e2 17 02 00 00 aa")
    inner += bytes.fromhex("e1 17 00 10 00") + bytes((flags2,))
    inner += b"\xe7\x3f" + ((-opcode_seed) & 65535).to_bytes(2, "big") + b"\x01"
    inner += READ + bytes.fromhex("0d 01 37") + number(1) + b"\xb7\x00"
    return program_bytes(
        root,
        (0x600, outer),
        (0x800, inner),
        (0x100, b"\x00\x01"),  # Valid status-line room for the references.
        (0x85, b"\x00\x90"),
    )
