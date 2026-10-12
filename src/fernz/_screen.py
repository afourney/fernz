"""Render public observation deltas into terminal cells for the optional CLI.

This frontend buffer is separate from VM checkpoints. Only the Textual frontend
imports it, so Rich is never required by the interpreter or simple CLI.
"""

import re
from collections import deque
from itertools import groupby

from rich.style import Style
from rich.text import Text

PALETTE = {
    "black": "#000000",
    "red": "#ff0000",
    "green": "#00ff00",
    "yellow": "#ffff00",
    "blue": "#0000ff",
    "magenta": "#ff00ff",
    "cyan": "#00ffff",
    "white": "#ffffff",
    "light-grey": "#bfbfbf",
    "medium-grey": "#808080",
    "dark-grey": "#404040",
}
# Keep interpreter defaults symbolic so rendered text inherits the active theme.
DEFAULT_STYLE = Style(color="default", bgcolor="default")
Cell = tuple[str, Style]


class ScreenBuffer:
    """Maintain two windows, lower-window scrollback, cursors and text styles."""

    def __init__(self, width: int = 80, height: int = 25) -> None:
        """Create a finite logical screen with at most 2,000 scrollback rows."""
        self.width, self.height = width, height
        self.reset()

    def reset(self) -> None:
        """Clear the screen and history, and restore the stream's default state."""
        self.window = self.split = 0
        self.buffered = True
        self.cursors = [(0, 0), (0, 0)]
        self.styles = [DEFAULT_STYLE, DEFAULT_STYLE]
        self.cells = [[self._blank() for _ in range(self.height)] for _ in range(2)]
        self.history: deque[list[Cell]] = deque(maxlen=2000)

    def _blank(self, window: int = 0) -> list[Cell]:
        style = self.styles[window]
        return [(" ", Style(color=style.color, bgcolor=style.bgcolor))] * self.width

    def apply(self, stream: str) -> None:
        """Consume complete public stream commands and escaped literal text."""
        position = 0
        text = []
        while position < len(stream):
            if stream.startswith("<<", position):
                text.append("<")
                position += 2
            elif stream[position] == "<":
                self.write("".join(text))
                text.clear()
                end = stream.index(">", position)
                self._command(stream[position + 1 : end].split())
                position = end + 1
            else:
                text.append(stream[position])
                position += 1
        self.write("".join(text))

    def _command(self, words: list[str]) -> None:
        name, *args = words
        if name == "reset":
            self.reset()
        elif name == "size":
            self.width, self.height = map(int, args)
            self.reset()  # The stream always emits size immediately after reset.
        elif name in ("top", "bottom"):
            self.window = int(name == "top")
        elif name == "split":
            self.split = int(args[0])
        elif name == "at":
            window = int(args[2] == "top") if len(args) == 3 else self.window
            self.cursors[window] = (int(args[0]) - 1, int(args[1]) - 1)
        elif name in ("bold", "italic", "invert"):
            attribute = "reverse" if name == "invert" else name
            self.styles[self.window] += Style(**{attribute: True})
        elif name == "normal":
            style = self.styles[self.window]
            self.styles[self.window] = Style(color=style.color, bgcolor=style.bgcolor)
        elif name == "color":
            foreground, background = (PALETTE.get(value, value) for value in args)
            self.styles[self.window] += Style(
                color=None if foreground == "current" else foreground,
                bgcolor=None if background == "current" else background,
            )
        elif name in ("font", "fixed"):
            pass  # Terminal cells already use a fixed-width font.
        elif name == "buffer":
            self.buffered = args[0] == "on"
        elif name == "clear":
            for window in (0, 1) if args[0] == "all" else (int(args[0] == "top"),):
                self.cells[window] = [self._blank(window) for _ in range(self.height)]
        elif name == "clear-line":
            row, column = self.cursors[self.window]
            if 0 <= row < self.height:
                self.cells[self.window][row][column:] = self._blank(self.window)[column:]
        else:
            raise ValueError(f"Unknown display command: {name}")

    def _newline(self) -> None:
        row, _ = self.cursors[self.window]
        row += 1
        if self.window == 0 and row >= self.height:
            row = self.height - 1
            if self.split < self.height:
                removed = self.cells[0].pop(self.split)
                if self.history or any(char != " " for char, _ in removed):
                    self.history.append(removed)
                self.cells[0].append(self._blank())
        self.cursors[self.window] = (row, 0)

    def write(self, text: str) -> None:
        """Write text or input echo, wrapping and scrolling only the lower window."""
        for word in re.findall(r"\n|[^\S\n]+|[^\s]+", text):
            _, column = self.cursors[self.window]
            if (
                self.window == 0
                and self.buffered
                and not word.isspace()
                and column
                and len(word) <= self.width
                and column + len(word) > self.width
            ):
                self._newline()
            for character in word:
                if character == "\n":
                    self._newline()
                    continue
                row, column = self.cursors[self.window]
                if column >= self.width:
                    self._newline()
                    row, column = self.cursors[self.window]
                limit = self.split if self.window else self.height
                if 0 <= row < limit:
                    self.cells[self.window][row][column] = (character, self.styles[self.window])
                self.cursors[self.window] = (row, column + 1)

    def render(self, window: int) -> Text:
        """Build styled terminal text without interpreting story text as markup."""
        rows = (
            self.cells[1][: self.split] if window else [*self.history, *self.cells[0][self.split :]]
        )
        result = Text(no_wrap=True, overflow="crop")
        for number, row in enumerate(rows):
            if number:
                result.append("\n")
            for style, cells in groupby(row, key=lambda cell: cell[1]):
                # Omit symbolic defaults from the Rich span, allowing widget CSS
                # to supply them even when the user switches themes later.
                rendered_style = style.without_color + Style(
                    color=None if style.color is None or style.color.is_default else style.color,
                    bgcolor=None
                    if style.bgcolor is None or style.bgcolor.is_default
                    else style.bgcolor,
                )
                result.append("".join(char for char, _ in cells), rendered_style)
        return result
