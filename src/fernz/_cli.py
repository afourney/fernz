"""Packaged command-line entry point for the Fernz library scaffold."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from fernz import FernzEnv


def main(argv: Sequence[str] | None = None) -> int:
    """Inspect a story or report the library's unimplemented execution.

    Return 1 for unimplemented execution, or 2 for an invalid story/path. Argument
    parsing exits with 0 for help and 2 for invalid command-line arguments.
    """
    parser = argparse.ArgumentParser(
        prog="fernz",
        description="Load raw V1-V8 Z-machine stories. Story execution is not implemented yet.",
    )
    parser.add_argument("game", type=Path, help="Path to a raw Z-machine story file.")
    parser.add_argument(
        "--inspect", action="store_true", help="Print story metadata as JSON and exit."
    )
    args = parser.parse_args(argv)

    try:
        env = FernzEnv(args.game)
    except (OSError, ValueError) as exc:
        print(f"fernz: {exc}", file=sys.stderr)
        return 2

    try:
        if args.inspect:
            story = env.story
            header = story.header
            print(
                json.dumps(
                    {
                        "version": header.version,
                        "release": header.release,
                        "serial": header.serial,
                        "file_size": len(story.data),
                        "story_size": story.size,
                        "static_memory": header.static_memory,
                        "high_memory": header.high_memory,
                        "entry_address": header.entry_address,
                        "entry_kind": "routine" if header.entry_is_routine else "instruction",
                        "checksum_valid": story.verify_checksum(),
                    },
                    indent=2,
                )
            )
            return 0
        env.reset()
    except NotImplementedError as exc:
        print(f"fernz: {exc}", file=sys.stderr)
        return 1
    finally:
        env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
