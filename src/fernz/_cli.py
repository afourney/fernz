"""Inspect stories or select an optional interactive frontend."""

import argparse
import json
import sys
from collections.abc import Sequence
from importlib.util import find_spec
from pathlib import Path

from fernz import ExecutionError, FernzEnv

from ._games import ensure_jericho_games
from ._simple_cli import SimpleCLI


def _game_path(path: Path) -> Path:
    """Use the exact path first, then the exact relative path under ./games.

    lstat preserves errors for existing paths, including dangling symlinks.
    Absolute paths have no distinct games-directory fallback.
    """
    try:
        path.lstat()
    except FileNotFoundError:
        if not path.is_absolute():
            candidate = Path("games") / path
            try:
                candidate.lstat()
            except FileNotFoundError:
                pass
            else:
                return candidate
    return path


def main(argv: Sequence[str] | None = None) -> int:
    """Inspect a story or play it until quit, EOF, or an execution error.

    Return 1 for execution errors, or 2 for an invalid story/path or download failure. Argument
    parsing exits with 0 for help and 2 for invalid command-line arguments.
    """
    parser = argparse.ArgumentParser(
        prog="fernz",
        description="Inspect V1-V8 stories or play supported V3/V4/V5/V8 games. Defaults to Textual when installed, otherwise simple mode.",
    )
    parser.add_argument(
        "game",
        nargs="?",
        type=Path,
        help="Raw story path; if missing, try the same relative path under ./games.",
    )
    parser.add_argument(
        "--download-games",
        nargs="?",
        const=Path("games"),
        type=Path,
        metavar="DESTINATION",
        help="Download the game suite and exit (default destination: ./games).",
    )
    parser.add_argument(
        "--screen-width", type=int, help="Logical columns (default: measure the terminal)."
    )
    parser.add_argument(
        "--screen-height", type=int, help="Logical rows (default: measure the available game area)."
    )
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
    if args.download_games is not None:
        if args.game is not None or args.inspect or args.simple or args.rich:
            parser.error("--download-games cannot be combined with a game or player/inspect flags")
        try:
            suite = ensure_jericho_games(args.download_games)
        except (OSError, RuntimeError) as exc:
            print(f"fernz: {exc}", file=sys.stderr)
            return 2
        print(f"Games available in {suite}")
        return 0
    if args.game is None:
        parser.error("a game is required unless --download-games is used")
    for name, value, limit in (
        ("width", args.screen_width, 255),
        ("height", args.screen_height, 254),
    ):
        if value is not None and not 1 <= value <= limit:
            parser.error(f"--screen-{name} must be between 1 and {limit}")

    env = None
    frontend = None

    def open_game(width: int, height: int) -> FernzEnv:
        # Textual calls this only after laying out its header and controls.
        nonlocal env
        env = FernzEnv(
            _game_path(args.game),
            save_handler=frontend.save if frontend else None,
            restore_handler=frontend.restore if frontend else None,
            screen_width=width,
            screen_height=height,
        )
        return env

    dimensions = {"screen_width": args.screen_width, "screen_height": args.screen_height}
    if not args.inspect:
        if args.simple:
            frontend = SimpleCLI(open_game, **dimensions)
        elif find_spec("textual") is not None:
            from ._rich_cli import RichCLI

            frontend = RichCLI(open_game, **dimensions)
        elif args.rich:
            parser.error("--rich requires Textual; install it with: pip install 'fernz[textual]'")
        else:
            frontend = SimpleCLI(open_game, **dimensions)

    try:
        if args.inspect:
            env = open_game(args.screen_width or 80, args.screen_height or 25)
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
        assert frontend is not None  # Non-inspection mode always selects a frontend.
        return frontend.run_repl()
    except KeyboardInterrupt:
        print()
        return 130
    except (OSError, NotImplementedError, ExecutionError, ValueError) as exc:
        print(f"fernz: {exc}", file=sys.stderr)
        return 2 if env is None else 1
    finally:
        if env is not None:
            env.close()


if __name__ == "__main__":
    raise SystemExit(main())
