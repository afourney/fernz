"""Object-opcode comparisons using only the standalone Frotz executable."""

import subprocess

import pytest

from fernz import FernzEnv

from .observation_helpers import plain_text
from .story_files import program_bytes
from .test_objects import object_memory

pytestmark = pytest.mark.reference


@pytest.mark.parametrize("branch_on_true", [True, False])
@pytest.mark.parametrize("parent", [0, 1, 65535])
def test_jin_zero_matches_frotz_branch_outcome(tmp_path, dfrotz, parent, branch_on_true):
    # An independently assembled jin 0,parent skips the X marker when its
    # branch is taken. Y verifies continued execution in both cases.
    code = b"\xc6\x0f\x00\x00" + parent.to_bytes(2, "big")
    code += bytes((0xC5 if branch_on_true else 0x45,))
    code += bytes.fromhex("e5 7f 58 e5 7f 59 bb ba")
    path = tmp_path / "jin-zero.z3"
    path.write_bytes(program_bytes(code))
    result = subprocess.run(
        [dfrotz, "-q", "-m", "-p", str(path)],
        input="",
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    # The reference may also print an object-zero diagnostic. Check the exact
    # story marker separately; Fernz does not add warnings to the transcript.
    expected = "Y" if (parent == 0) == branch_on_true else "XY"
    markers = [line.strip() for line in result.stdout.splitlines() if line.strip() in ("Y", "XY")]
    assert markers == [expected], (result.stdout, result.stderr)
    env = FernzEnv(path)
    try:
        assert plain_text(env.reset()[0]) == expected + "\n"
        assert env.done
    finally:
        env.close()


@pytest.mark.parametrize(
    "code,expected",
    [
        ("0a 00 00 c5 e5 7f 58 e5 7f 59 bb ba", ["XY"]),
        ("0a 00 1f 45 e5 7f 58 e5 7f 59 bb ba", ["Y"]),
        ("12 01 20 10 e6 bf 10 bb ba", ["0"]),
        ("d2 0f 00 01 ff ff 10 e6 bf 10 bb ba", ["0"]),
        ("0e 01 02 93 01 10 e6 bf 10 bb 92 02 10 c2 e6 bf 10 bb ba", ["2", "1"]),
    ],
    ids=(
        "zero-attribute-false",
        "zero-attribute-inverted",
        "property-32",
        "property-65535",
        "cycle",
    ),
)
def test_historical_object_operations_match_frotz(tmp_path, dfrotz, code, expected):
    data = bytearray(object_memory().story.data)
    program = bytes.fromhex(code)
    data[0x401 : 0x401 + len(program)] = program
    path = tmp_path / "object-operations.z3"
    path.write_bytes(data)
    reference = subprocess.run(
        [dfrotz, "-q", "-m", "-p", str(path)],
        input="",
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    # Object-zero diagnostics belong to the reference host, not story output.
    lines = [line for line in reference.stdout.splitlines() if line in {"XY", "Y", "0", "1", "2"}]
    assert lines == expected
    env = FernzEnv(path)
    try:
        assert plain_text(env.reset()[0]).splitlines() == expected
        assert env.done
    finally:
        env.close()


@pytest.mark.parametrize(
    "code,chunks,expected",
    [
        (
            "93 00 10 92 00 11 c2 91 00 12 c2 11 00 01 13 12 00 01 14 13 00 00 15 e6 bf 10 e6 bf 11 e6 bf 12 e6 bf 13 e6 bf 14 e6 bf 15 bb ba",
            (),
            "000000",
        ),
        ("9a 00 bb ba", ((0x7C, b"\x02\x00"), (0x200, bytes.fromhex("01 98 e8"))), "abc"),
        ("e0 3f 02 80 10 e6 bf 10 bb ba", ((0x500, bytes.fromhex("02 00 0b 00 17 b8")),), "23"),
        ("f5 7f 01 f5 5f 03 01 f5 53 03 02 00 08 f5 5f 03 03 f5 5f 03 04 e5 7f 41 bb ba", (), "A"),
    ],
)
def test_legacy_v3_execution_matches_standalone(tmp_path, dfrotz, code, chunks, expected):
    path = tmp_path / "legacy.z3"
    path.write_bytes(program_bytes(bytes.fromhex(code), *chunks))
    reference = subprocess.run(
        [dfrotz, "-q", "-m", "-p", str(path)],
        input="",
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    # Frotz can add diagnostics for undefined legacy operations before output.
    assert reference.stdout.rstrip().endswith(expected), (reference.stdout, reference.stderr)
    env = FernzEnv(path)
    try:
        assert plain_text(env.reset()[0]) == expected + "\n"
        assert env.done
    finally:
        env.close()


def test_malformed_dictionary_lookup_matches_public_references(tmp_path, dfrotz):
    from jericho import FrotzEnv

    from .test_input import malformed_dictionary_story

    path = tmp_path / "dictionary.z3"
    path.write_bytes(malformed_dictionary_story())
    for command, expected in (
        ("foo", 0x304),
        ("for", 0),
        ("forget", 0),
        ("format", 0),
        ("fort", 0x31C),
        ("fox", 0x322),
        ("foxes", 0x328),
    ):
        env = FrotzEnv(str(path), seed=42)
        try:
            env.reset()
            assert [
                line
                for line in plain_text(env.step(command)[0]).splitlines()
                if line.startswith("R=")
            ] == [f"R={expected}"]
        finally:
            env.close()
        reference = subprocess.run(
            [dfrotz, "-q", "-m", "-p", str(path)],
            input=command + "\n",
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert reference.returncode == 0, reference.stderr
        assert f"R={expected}" in reference.stdout.splitlines()


def test_absent_object_name_placeholder_matches_public_jericho(tmp_path):
    from jericho import FrotzEnv

    path = tmp_path / "unnamed.z3"
    path.write_bytes(program_bytes(bytes.fromhex("9a 00 bb ba"), (0x7C, b"\x02\x00")))
    reference = FrotzEnv(str(path), seed=42)
    env = FernzEnv(path)
    try:
        assert plain_text(env.reset()[0]) == plain_text(reference.reset()[0]) == "object#0\n"
    finally:
        reference.close()
        env.close()
