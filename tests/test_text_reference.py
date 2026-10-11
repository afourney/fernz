"""Measure V3 tab output using Jericho's public API and an independent story."""

import warnings

import pytest

from fernz import FernzEnv

from .observation_helpers import plain_text
from .story_files import program_bytes, zchars

pytestmark = pytest.mark.reference


def test_v3_tab_extension_matches_jericho_transcript(tmp_path):
    from jericho import FrotzEnv

    # Leading, middle, consecutive, and trailing tabs emitted by print_char,
    # followed by tabs encoded in an inline Z-string. No input or status line.
    code = bytearray()
    for char in "\tA\tB\n\t\tC\nD\t\n":
        code.extend((0xE5, 0x7F, 13 if char == "\n" else ord(char)))
    code.extend(b"\xb2" + zchars(5, 6, 0, 9, 6, 5, 6, 0, 9, 7) + b"\xbb\xba")
    story = tmp_path / "tabs.z3"
    story.write_bytes(program_bytes(bytes(code)))
    expected = "   A   B\n      C\nD   \n   a   b\n"

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message="Game .* is not fully supported", category=UserWarning
        )
        reference = FrotzEnv(str(story), seed=12)
    env = FernzEnv(story, seed=12)
    try:
        assert plain_text(reference.reset()[0]) == expected
        assert plain_text(env.reset()[0]) == expected
    finally:
        env.close()
        reference.close()
