"""Independent V3 probe for deferred host seeds and environment copies."""

from .save_story import number
from .story_files import READ, program_bytes


def seed_story():
    """Draw on startup/input, reseed with random 0, then restart on third input."""
    draw = bytes.fromhex("e7 3f 7f ff 13") + number(19)
    code = draw + READ + draw + READ + bytes.fromhex("e7 7f 00 13") + draw + READ + b"\xb7"
    return program_bytes(code, (0x100, b"\x00\x01"), (0x85, b"\x00\x90"))
