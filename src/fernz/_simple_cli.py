"""Dependency-free terminal REPL, including redirected input and output."""

import sys
from collections.abc import Callable
from pathlib import Path
from shutil import get_terminal_size

from ._cli_files import write_save
from ._env import FernzEnv


class SimpleCLI:
    """Read edited lines and stream plain output immediately to the terminal."""

    def __init__(
        self,
        open_game: Callable[[int, int], FernzEnv],
        *,
        screen_width: int | None = None,
        screen_height: int | None = None,
    ) -> None:
        """Defer game creation until the terminal dimensions are known."""
        self.open_game = open_game
        self.screen_width, self.screen_height = screen_width, screen_height

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

    def run_repl(self) -> int:
        """Run until VM quit or EOF, leaving exception reporting to main."""
        width, height = get_terminal_size((80, 25)) if sys.stdout.isatty() else (80, 25)
        env = self.open_game(
            self.screen_width if self.screen_width is not None else max(1, min(255, width)),
            self.screen_height if self.screen_height is not None else max(1, min(254, height)),
        )
        env.reset()
        while not env.done:
            line = sys.stdin.readline()
            if not line:
                break
            env.step(line.removesuffix("\n").removesuffix("\r"))
        return 0
