"""Inspect stories or play through a minimal text terminal."""

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from tempfile import NamedTemporaryFile

from fernz import ExecutionError, FernzEnv


def _write_output(text: str) -> None:
    print(text, end="", flush=True)


def _file_path(operation: str) -> Path | None:
    _write_output(f"{operation} file (blank cancels): ")
    name = sys.stdin.readline().strip()
    return Path(name).expanduser() if name else None


def _save_file(data: bytes) -> bool:
    temporary = None
    try:
        path = _file_path("Save")
        if path is None:
            return False
        if path.exists():
            _write_output("Overwrite existing file? [y/N]: ")
            if sys.stdin.readline().strip().lower() not in ("y", "yes"):
                return False
        # Publish only a complete save, leaving an existing file intact if a
        # write fails. The temporary file is on the same filesystem as the target.
        with NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as file:
            temporary = Path(file.name)
            file.write(data)
        os.replace(temporary, path)
        return True
    except OSError as exc:
        print(f"fernz: {exc}", file=sys.stderr)
        return False
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _restore_file() -> bytes | None:
    try:
        path = _file_path("Restore")
        return path.read_bytes() if path is not None else None
    except OSError as exc:
        print(f"fernz: {exc}", file=sys.stderr)
        return None


def main(argv: Sequence[str] | None = None) -> int:
    """Inspect a story or play it until quit, EOF, or an execution error.

    Return 1 for execution errors, or 2 for an invalid story/path. Argument
    parsing exits with 0 for help and 2 for invalid command-line arguments.
    """
    parser = argparse.ArgumentParser(
        prog="fernz",
        description="Inspect V1-V8 stories or play supported V3 games. Use EOF to exit.",
    )
    parser.add_argument("game", type=Path, help="Path to a raw Z-machine story file.")
    parser.add_argument(
        "--inspect", action="store_true", help="Print story metadata as JSON and exit."
    )
    args = parser.parse_args(argv)

    try:
        env = FernzEnv(
            args.game,
            save_handler=_save_file,
            restore_handler=_restore_file,
            output_handler=_write_output,
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
        env.reset()
        while not env.done:
            line = sys.stdin.readline()
            if not line:
                break
            env.step(line.removesuffix("\n").removesuffix("\r"))
    except KeyboardInterrupt:
        print()
        return 130
    except (NotImplementedError, ExecutionError, ValueError) as exc:
        print(f"fernz: {exc}", file=sys.stderr)
        return 1
    finally:
        env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
