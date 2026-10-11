"""Check accepted input bytes and parse records through the Frotz executable."""

import re
import subprocess

import pytest

from fernz import FernzEnv

from .story_files import READ, program_bytes

pytestmark = pytest.mark.reference


@pytest.mark.parametrize(
    "capacity,line",
    [(2, "A"), (5, "LOOK"), (20, "A,B zz"), (20, ""), (20, "A?B"), (20, "?"), (20, "X" * 25)],
)
def test_v3_input_buffers_against_frotz(tmp_path, dfrotz, capacity, line):
    # Print input bytes and two parse slots, including untouched canaries.
    addresses = [*range(0x281, 0x281 + capacity + 1), *range(0x2A1, 0x2AA)]
    code = bytearray(READ)
    for address in addresses:
        code.extend(bytes.fromhex("e5 7f 52 e5 7f 3d d0 1f"))  # Print R=; loadb.
        code.extend(address.to_bytes(2, "big") + bytes.fromhex("00 10 e6 bf 10 bb"))
    code.append(0xBA)  # quit
    story = tmp_path / "input.z3"
    story.write_bytes(
        program_bytes(
            bytes(code),
            (0x280, bytes((capacity,)) + b"\xcc" * (capacity + 1)),
            (0x2A0, b"\x02" + b"\xcc" * 9),
            (0x300, b"\x01,\x04\x00\x00"),  # Empty dictionary with comma separator.
            (0x100, b"\x00\x01"),  # Current room is object 1 for the V3 status line.
            (0x85, b"\x00\x90"),  # Object 1 has an empty name/property list at 0x90.
        )
    )
    reference = subprocess.run(
        [dfrotz, "-q", "-m", "-p", "-s", "42", str(story)],
        input=line + "\n",
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    assert reference.stderr == ""
    env = FernzEnv(story, seed=42)
    try:
        env.reset()
        expected = [int(n) for n in re.findall(r"^R=(\d+)$", reference.stdout, re.MULTILINE)]
        actual = [int(n) for n in re.findall(r"^R=(\d+)$", env.step(line)[0], re.MULTILINE)]
        assert len(expected) == len(actual) == len(addresses)
        if line == "X" * 25:
            # This dumb frontend passes all 25 characters despite capacity 20.
            # Fernz reserves NUL within the declared V3 buffer: it accepts 19,
            # leaves the canary intact, and records the shorter parsed word.
            assert expected == [120] * 21 + [1, 0, 0, 25, 1] + [204] * 4
            assert actual == [120] * 19 + [0, 204, 1, 0, 0, 19, 1] + [204] * 4
        else:
            assert actual == expected
    finally:
        env.close()
