"""Independent V3/V5 probe for deferred host seeds and environment copies."""

from .save_story import number
from .story_files import READ, program_bytes


def seed_story(version=3):
    """Draw on startup/input, reseed with random 0, then restart on third input."""
    draw = bytes.fromhex("e7 3f 7f ff 13") + number(19)
    read = READ if version == 3 else bytes.fromhex("e2 17 02 80 01 00") + READ + b"\x10"
    code = draw + read + draw + read + bytes.fromhex("e7 7f 00 13") + draw + read + b"\xb7"
    table = (0x85, b"\x00\x90") if version == 3 else (0xCA, b"\x00\xcc")
    return program_bytes(code, (0x100, b"\x00\x01"), table, version=version)
