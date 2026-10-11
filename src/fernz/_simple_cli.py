"""Dependency-free terminal REPL, including redirected input and output."""

import sys
from pathlib import Path

from ._cli_files import write_save
from ._env import FernzEnv


class SimpleCLI:
    """Read edited lines and stream plain output immediately to the terminal."""

    @staticmethod
    def output(text: str) -> None:
        """Write raw output, including prompts preceding storage callbacks."""
        print(text, end="", flush=True)

    @staticmethod
    def _file_path(operation: str) -> Path | None:
        SimpleCLI.output(f"{operation} file (blank cancels): ")
        name = sys.stdin.readline().strip()
        return Path(name).expanduser() if name else None

    @staticmethod
    def save(data: bytes) -> bool:
        """Prompt for a path and confirm before replacing an existing save."""
        try:
            path = SimpleCLI._file_path("Save")
            if path is None:
                return False
            if path.exists():
                SimpleCLI.output("Overwrite existing file? [y/N]: ")
                if sys.stdin.readline().strip().lower() not in ("y", "yes"):
                    return False
            write_save(path, data)
            return True
        except OSError as exc:
            print(f"fernz: {exc}", file=sys.stderr)
            return False

    @staticmethod
    def restore() -> bytes | None:
        """Prompt for a saved game; cancellation and failed reads report failure."""
        try:
            path = SimpleCLI._file_path("Restore")
            return path.read_bytes() if path is not None else None
        except OSError as exc:
            print(f"fernz: {exc}", file=sys.stderr)
            return None

    @staticmethod
    def run_repl(env: FernzEnv) -> int:
        """Run until VM quit or EOF, leaving exception reporting to main."""
        env.reset()
        while not env.done:
            line = sys.stdin.readline()
            if not line:
                break
            env.step(line.removesuffix("\n").removesuffix("\r"))
        return 0
