"""Regenerate the current codec's synthetic fixtures, without ROMs or Jericho.

Run from the repository root:
    python -m tests.scripts.generate_checkpoint_fixtures
"""

from dataclasses import replace
from pathlib import Path
from random import Random

from fernz import FernzEnv, Story

from ..story_files import READ, program_bytes


def main() -> None:
    """Write deterministic predictable and ordinary-mode schema-5 checkpoints."""
    read = READ + b"\x10"
    story = Story(
        program_bytes(read + bytes.fromhex("e7 3f 7f ff 11 e6 bf 11") + read + b"\xba", version=5)
    )
    env = FernzEnv(story, seed=42)
    env.reset()
    state = env.get_state()
    root = Path(__file__).resolve().parents[1] / "vectors"
    (root / "checkpoint_schema5.json").write_bytes(state.to_bytes())
    ordinary = replace(state.rng, host_seed=None, state=0, python_state=Random(12345).getstate())
    (root / "checkpoint_schema5_python_rng.json").write_bytes(
        replace(state, rng=ordinary).to_bytes()
    )


if __name__ == "__main__":
    main()
