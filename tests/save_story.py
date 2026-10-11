"""Independent V3 SAVE/RESTORE probes assembled from the opcode specification."""

from .story_files import READ, program_bytes


def number(variable):
    return bytes.fromhex("e5 7f 52 e5 7f 3d e6 bf") + bytes((variable, 0xBB))


def call(address, args, store):
    values = (address // 2, *args)
    types = sum((0 if i < len(values) else 3) << (6 - 2 * i) for i in range(4))
    return bytes((0xE0, types)) + b"".join(v.to_bytes(2, "big") for v in values) + bytes((store,))


def jump(address, target):
    return b"\x8c" + ((target - address - 1) & 65535).to_bytes(2, "big")


def save_story(*, high=False):
    """Save inside nested calls; a root command beginning with 'r' restores.

    Three frames hold distinct stack sentinels. Saving prints the callee locals
    and its stack value, draws a random number, then waits for a command before
    returning through the callers. The root then accepts another save/restore.
    """
    outer_address, inner_address = (0x10000, 0x11000) if high else (0x600, 0x800)
    root = bytes.fromhex("e8 3f 11 11") + READ + bytes.fromhex("d0 1f 02 80 01 13 41 13 72")
    branch_end = 0x401 + len(root) + 2
    root += b"\x00\x00"
    root += call(outer_address, (7,), 20) + number(20) + number(0)
    root += jump(0x401 + len(root), 0x401)
    restore_address = 0x401 + len(root)
    root = (
        root[: branch_end - 0x401 - 2]
        + (0x8000 | (restore_address - branch_end + 2)).to_bytes(2, "big")
        + root[branch_end - 0x401 :]
    )
    root += bytes.fromhex("b6 c2 e5 7f 46 bb b9")
    root += jump(0x401 + len(root), 0x401)

    outer = bytes.fromhex("02 00 11 00 12 e8 3f 22 22")
    outer += call(inner_address, (7, 8, 9), 1)
    outer += number(2) + number(1) + number(0) + bytes.fromhex("ab 01")
    inner = bytes.fromhex("03 44 44 55 55 66 66 e8 3f 33 33 b5 c6 e5 7f 46 ba e5 7f 53 bb")
    inner += number(1) + number(2) + number(3) + number(0)
    inner += bytes.fromhex("e7 3f 7f ff 01") + number(1) + READ + bytes.fromhex("9b 2a")
    return program_bytes(
        root,
        (outer_address, outer),
        (inner_address, inner),
        (0x100, b"\x00\x01"),  # Valid status-line room for the reference executable.
        (0x85, b"\x00\x90"),
        size=0x12000 if high else 4096,
    )
