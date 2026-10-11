"""Display output measured through public APIs on independent synthetic stories."""

import pytest

from fernz import FernzEnv

from .observation_helpers import stream_events
from .story_files import program_bytes
from .test_observations import say
from .test_restart_reference import synthetic_reference

pytestmark = [pytest.mark.reference, pytest.mark.smoke]


@pytest.mark.parametrize("version", (3, 5, 8))
def test_both_windows_emit_in_order_like_public_reference(tmp_path, version):
    code = say("LOWER-A\n") + bytes.fromhex("ea 7f 03 eb 7f 01") + say("UPPER-A\n")
    if version >= 5:
        code += bytes.fromhex("ef 5f 01 01 f1 7f 02") + say("UPPER-B\n")
        code += bytes.fromhex("ee 7f 01 ed 7f 01")
    code += bytes.fromhex("ea 7f 00 eb 7f 00") + say("LOWER-B\n") + b"\xba"
    path = tmp_path / f"display.z{version}"
    path.write_bytes(program_bytes(code, version=version))
    reference, env = synthetic_reference(path, 42), FernzEnv(path, seed=42)
    try:
        expected = reference.reset()[0]
        observation, _ = env.reset()
        assert observation.text == expected
        assert "".join(v for k, v in stream_events(observation.stream) if k == "text") == expected
        assert "UPPER-A" in expected
        assert "<split 0>" in observation.stream
    finally:
        reference.close()
        env.close()


def test_configured_geometry_matches_public_reference_header(tmp_path):
    path = tmp_path / "geometry.z5"
    path.write_bytes(program_bytes(say("GEOMETRY\n") + b"\xba", version=5))
    reference = synthetic_reference(path, 42)
    try:
        reference.reset()
        header = reference.get_state()[0]
        env = FernzEnv(path, screen_width=int(header[0x21]), screen_height=int(header[0x20]))
        env.reset()
        assert env.get_state().ram[0x20:0x28] == header[0x20:0x28].tobytes()
    finally:
        reference.close()
