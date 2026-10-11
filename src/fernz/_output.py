"""Text-only window bookkeeping and nested memory output (Standard §§7-8)."""

from dataclasses import replace

from ._errors import ExecutionError
from ._memory import Memory
from ._state import OutputState
from ._text import Text


class Output:
    """Capture lower-window prose, tracking upper-window cursors separately.

    This is a transcript interface, not a terminal renderer. Upper-window
    redraws do not enter observations. Cursor queries still see logical screen
    coordinates; stream 3 receives text independently of the selected window.
    """

    width = 80
    height = 25

    def __init__(self, memory: Memory, state: OutputState | None = None) -> None:
        """Bind output tables to memory and restore immutable display state."""
        self.memory = memory
        self.state = state if state is not None else OutputState()

    def emit(self, text: str) -> str:
        """Write redirected ZSCII or advance the cursor and return narrative."""
        streams = self.state.memory_streams
        if streams:
            address, count = streams[-1]
            data = Text(self.memory).encode_output(text)
            self.memory.write_bytes(address + 2 + count, data)
            self.state = replace(
                self.state, memory_streams=(*streams[:-1], (address, count + len(data)))
            )
            return ""
        row, column = self.state.cursors[self.state.window]
        last_row = max(1, self.state.split_lines) if self.state.window else self.height
        for character in text:
            if character == "\n":
                row, column = min(last_row, row + 1), 1
            else:
                if column > self.width:
                    row, column = min(last_row, row + 1), 1
                column += 1
        self._cursor(row, column)
        return text if self.state.window == 0 else ""

    def memory_stream(self, table: int | None) -> None:
        """Push a stream-3 table, or finish the innermost selected stream."""
        streams = self.state.memory_streams
        if table is None:
            if not streams:
                return
            address, count = streams[-1]
            self.memory.write_word(address, count)
            self.state = replace(self.state, memory_streams=streams[:-1])
        else:
            if len(streams) == 16:
                raise ExecutionError("Memory output nesting exceeds 16 streams")
            if table < 64:
                raise ExecutionError("Memory output requires a dynamic-memory table")
            self.memory.write_word(table, 0)
            self.state = replace(self.state, memory_streams=(*streams, (table, 0)))

    def _cursor(self, row: int, column: int) -> None:
        cursors = list(self.state.cursors)
        cursors[self.state.window] = (row, column)
        self.state = replace(self.state, cursors=tuple(cursors))

    def split(self, lines: int) -> None:
        """Resize the upper window, retaining separate cursor positions."""
        if not 0 <= lines <= self.height:
            raise ExecutionError("Upper window height is outside the screen")
        lower, upper = self.state.cursors
        if upper[0] > lines:
            upper = (1, 1)
        if lower[0] <= lines:
            lower = (min(self.height, lines + 1), 1)
        self.state = replace(self.state, split_lines=lines, cursors=(lower, upper))

    def select(self, window: int) -> None:
        """Select one of the two text windows, resetting the upper cursor."""
        if window not in (0, 1):
            raise ExecutionError(f"Invalid text window {window}")
        self.state = replace(self.state, window=window)
        if window == 1:
            self._cursor(1, 1)

    def move(self, row: int, column: int) -> None:
        """Position the upper-window cursor; lower-window positioning is ignored."""
        if self.state.window == 0:
            return
        if not 1 <= row <= self.height or column < 1:
            raise ExecutionError("Cursor is outside the upper window")
        if column > self.width:
            # Saves made on wider displays can retain story-owned cursor
            # columns. V4/V5 executable probes move to column 1 on the
            # requested row, rather than storing an off-screen position.
            if self.memory.story.header.version in (4, 5):
                column = 1
            else:
                raise ExecutionError("Cursor is outside the upper window")
        if row > self.state.split_lines:
            # §8 remarks recommend an implicit split for V4/V5 box quotes
            # whose requested cursor extends below the current upper window.
            if self.memory.story.header.version not in (4, 5):
                raise ExecutionError("Cursor is outside the upper window")
            self.split(row)
        self._cursor(row, column)

    def font(self, number: int) -> int:
        """Choose a supported font for the current window, or query with zero."""
        if number not in (0, 1, 4):
            return 0
        fonts = list(self.state.fonts)
        previous = fonts[self.state.window]
        if number:
            fonts[self.state.window] = number
            self.state = replace(self.state, fonts=tuple(fonts))
        return previous

    def erase(self, window: int) -> None:
        """Reset the specified logical window, preserving the emitted transcript."""
        if window not in (-2, -1, 0, 1):
            raise ExecutionError(f"Invalid window to erase: {window}")
        if window == -1:
            self.state = replace(self.state, window=0, split_lines=0, cursors=((1, 1), (1, 1)))
        elif window >= 0:
            cursors = list(self.state.cursors)
            cursors[window] = (
                min(self.height, self.state.split_lines + 1) if window == 0 else 1,
                1,
            )
            self.state = replace(self.state, cursors=tuple(cursors))
