"""Inspect stories or select an optional interactive frontend."""

import argparse
import json
import sys
from collections.abc import Sequence
from importlib.util import find_spec
from pathlib import Path

from fernz import ExecutionError, FernzEnv

from ._simple_cli import SimpleCLI


def main(argv: Sequence[str] | None = None) -> int:
    """Inspect a story or play it until quit, EOF, or an execution error.

    Return 1 for execution errors, or 2 for an invalid story/path. Argument
    parsing exits with 0 for help and 2 for invalid command-line arguments.
    """
    parser = argparse.ArgumentParser(
        prog="fernz",
        description="Inspect V1-V8 stories or play supported V3/V5/V8 games. Defaults to Textual when installed, otherwise simple mode.",
    )
    parser.add_argument("game", type=Path, help="Path to a raw Z-machine story file.")
    parser.add_argument(
        "--screen-width", type=int, default=80, help="Logical columns (default: 80)."
    )
    parser.add_argument("--screen-height", type=int, default=25, help="Logical rows (default: 25).")
    parser.add_argument(
        "--inspect", action="store_true", help="Print story metadata as JSON and exit."
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--simple", action="store_true", help="Use the plain terminal REPL (also for pipes)."
    )
    modes.add_argument(
        "--rich", action="store_true", help="Use the Textual interface (requires fernz[textual])."
    )
    args = parser.parse_args(argv)
    frontend = None
    if not args.inspect:
        if args.simple:
            frontend = SimpleCLI()
        elif find_spec("textual") is not None:
            from ._rich_cli import RichCLI

            frontend = RichCLI()
        elif args.rich:
            parser.error("--rich requires Textual; install it with: pip install 'fernz[textual]'")
        else:
            frontend = SimpleCLI()

    try:
        env = FernzEnv(
            args.game,
            save_handler=frontend.save if frontend else None,
            restore_handler=frontend.restore if frontend else None,
            output_handler=frontend.output if frontend else None,
            screen_width=args.screen_width,
            screen_height=args.screen_height,
        )
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
        return frontend.run_repl(env)
    except KeyboardInterrupt:
        print()
        return 130
    except (NotImplementedError, ExecutionError, ValueError) as exc:
        print(f"fernz: {exc}", file=sys.stderr)
        return 1
    finally:
        env.close()


if __name__ == "__main__":
    raise SystemExit(main())
