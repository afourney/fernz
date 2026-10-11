"""Object-opcode comparisons using only the standalone Frotz executable."""

import subprocess

import pytest

from fernz import FernzEnv

from .story_files import program_bytes

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
        assert env.reset()[0] == expected + "\n"
        assert env.done
    finally:
        env.close()
