"""Packaged command-line entry point for the Fernz library scaffold."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from fernz import FernzEnv


def main(argv: Sequence[str] | None = None) -> int:
    """Validate a game path and report the library's unimplemented execution.

    Return 1 for unimplemented execution, or 2 for an invalid path. Argument
    parsing exits with 0 for help and 2 for invalid command-line arguments.
    """
    parser = argparse.ArgumentParser(
        prog="fernz",
        description="Fernz Z-machine player scaffold. Story execution is not implemented yet.",
    )
    parser.add_argument("game", type=Path, help="Path to an existing game file.")
    args = parser.parse_args(argv)

    try:
        env = FernzEnv(args.game)
    except (OSError, ValueError) as exc:
        print(f"fernz: {exc}", file=sys.stderr)
        return 2

    try:
        env.reset()
    except NotImplementedError as exc:
        print(f"fernz: {exc}", file=sys.stderr)
        return 1
    finally:
        env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
