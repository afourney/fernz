"""Hand-assembled random-opcode probes; no compiler or interpreter source used."""

import re
from collections.abc import Sequence

from .story_files import put_word, story_bytes


def random_story(operands: Sequence[int], version: int = 3) -> bytes:
    """Print one labelled result for each operand, then quit without requesting input."""
    code = bytearray()
    for operand in operands:
        assert -32768 <= operand <= 32767
        # print_char 'R'; print_char '='; random <large constant> -> global32;
        # print_num global32; new_line. Avoid the three V3 status globals.
        code.extend(bytes.fromhex("e5 7f 52 e5 7f 3d e7 3f"))
        code.extend((operand & 0xFFFF).to_bytes(2, "big"))
        code.extend(bytes.fromhex("20 e6 bf 20 bb"))
    code.append(0xBA)  # quit; avoids terminal redraws caused by line input.
    size = max(4096, ((0x401 + len(code) + 7) // 8) * 8)
    data = bytearray(story_bytes(version, size))
    # V6's main routine begins at 0x400 with zero locals. Other versions' PC
    # starts at 0x401. The instruction stream is identical in all versions.
    data[0x401 : 0x401 + len(code)] = code
    if version >= 3:
        put_word(data, 0x1C, sum(data[64:]) & 0xFFFF)
    return bytes(data)


def results(output: str, count: int) -> list[int]:
    """Extract exactly the expected number of printed results, ignoring terminal spacing."""
    values = [
        int(value) for value in re.findall(r"^R=(\d+)$", output.replace("\r\n", "\n"), re.MULTILINE)
    ]
    assert len(values) == count, f"Expected {count} RNG results, got {len(values)}"
    return values
