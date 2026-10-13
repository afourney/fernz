"""Text-only window bookkeeping and nested memory output (Standard §§7-8)."""

from dataclasses import replace
from functools import cached_property

from ._errors import ExecutionError
from ._memory import Memory
from ._observation import COLOURS, ScreenOutputClipped
from ._state import LATE_SCREEN_VERSIONS, OutputState
from ._text import Text


class Output:
    """Track logical windows and collect an ordered, escaped display stream.

    This is a display protocol, not a rendered screen buffer. Both windows'
    writes are retained, even if later overwritten or erased. Stream 3 remains
    independent of the display and never enters either observation field.
    """

    def __init__(self, memory: Memory, state: OutputState | None = None) -> None:
        """Bind output tables to memory and restore immutable display state."""
        self.memory = memory
        self.state = state if state is not None else OutputState()
        self._stream: list[str] = []
        self._clipped: ScreenOutputClipped | None = None

    @cached_property
    def text(self) -> Text:
        """Return the stream-3 encoder, created when first needed."""
        return Text(self.memory)

    @property
    def width(self) -> int:
        """Return the logical width in fixed-width characters."""
        return self.state.width

    @property
    def height(self) -> int:
        """Return the logical screen height in rows."""
        return self.state.height

    def command(self, name: str, *arguments: object) -> None:
        """Append an interpreter-owned display command."""
        self._stream.append("<" + " ".join(map(str, (name, *arguments))) + ">")

    def start(self) -> None:
        """Initialize a consumer's display at an environment reset boundary."""
        self.command("reset")
        self.command("size", self.width, self.height)
        self.command("bottom")
        if self.memory.story.header.version <= 4:
            self._cursor(self.height, 1)
            self.command("at", self.height, 1)

    def drain(self) -> str:
        """Return this call's stream, joining adjacent text without extra tags."""
        result = "".join(self._stream)
        self._stream.clear()
        return result

    def emit(self, text: str) -> str:
        """Write redirected ZSCII or advance the cursor and return narrative."""
        streams = self.state.memory_streams
        if streams:
            address, count = streams[-1]
            data = self.text.encode_output(text)
            self.memory.write_bytes(address + 2 + count, data)
            self.state = replace(
                self.state, memory_streams=(*streams[:-1], (address, count + len(data)))
            )
            return ""
        self._stream.append(text.replace("<", "<<"))
        row, column = self.state.cursors[self.state.window]
        # Upper-window painting never scrolls or returns to a visible row on
        # overflow. Keep coordinates representable by get_cursor's word fields.
        last_row = 0xFFFF if self.state.window else self.height
        if self.state.window and self.memory.story.header.version == 3:
            last_row = max(1, self.state.split_lines)
        for character in text:
            if character == "\n":
                row, column = min(last_row, row + 1), 1
            else:
                if column > self.width:
                    row, column = min(last_row, row + 1), 1
                if self.state.window and row > self.height:
                    self._record_clipping(row, column)
                column += 1
        self._cursor(row, column)
        return text

    def _record_clipping(self, row: int, column: int) -> None:
        previous = self._clipped
        self._clipped = ScreenOutputClipped(
            self.width,
            self.height,
            self.state.window,
            1 if previous is None else previous.clipped_cells + 1,
            row if previous is None else min(previous.min_row, row),
            row if previous is None else max(previous.max_row, row),
            column if previous is None else min(previous.min_column, column),
            column if previous is None else max(previous.max_column, column),
        )

    def drain_diagnostics(self) -> tuple[ScreenOutputClipped, ...]:
        """Report clipping once per execution boundary, outside saved state."""
        result = () if self._clipped is None else (self._clipped,)
        self._clipped = None
        return result

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

    def _cursor_command(self, window: int) -> None:
        """Report a cursor move without changing the selected window."""
        target = () if window == self.state.window else ("top" if window else "bottom",)
        self.command("at", *self.state.cursors[window], *target)

    def split(self, lines: int) -> None:
        """Resize the upper window, retaining separate cursor positions."""
        if not 0 <= lines <= 0xFFFF:
            raise ExecutionError("Upper window height is outside the screen")
        if lines > self.height:
            if self.memory.story.header.version not in LATE_SCREEN_VERSIONS:
                raise ExecutionError("Upper window height is outside the screen")
            lines = self.height
        previous = self.state.cursors
        lower, upper = previous
        if upper[0] > lines:
            upper = (1, 1)
        if lower[0] <= lines:
            lower = (min(self.height, lines + 1), 1)
        self.state = replace(self.state, split_lines=lines, cursors=(lower, upper))
        self.command("split", lines)
        if self.memory.story.header.version == 3:
            self.command("clear", "top")
        for window, cursor in enumerate(self.state.cursors):
            if cursor != previous[window]:
                self._cursor_command(window)

    def select(self, window: int) -> None:
        """Select one of the two text windows, resetting the upper cursor."""
        if window not in (0, 1):
            raise ExecutionError(f"Invalid text window {window}")
        self.state = replace(self.state, window=window)
        self.command("top" if window else "bottom")
        if window == 1:
            self._cursor(1, 1)
            self.command("at", 1, 1)

    def move(self, row: int, column: int) -> None:
        """Position the upper-window cursor; lower-window positioning is ignored."""
        if self.state.window == 0:
            return
        if not 1 <= row <= 0xFFFF or column < 1:
            raise ExecutionError("Cursor is outside the upper window")
        if column > self.width:
            # Saves made on wider displays can retain story-owned cursor
            # columns. V4/V5 executable probes move to column 1 on the
            # requested row, rather than storing an off-screen position.
            if self.memory.story.header.version in LATE_SCREEN_VERSIONS:
                column = 1
            else:
                raise ExecutionError("Cursor is outside the upper window")
        if row > self.state.split_lines:
            # §8 remarks recommend an implicit split for V4/V5 box quotes
            # (also V7/V8 under §1 remarks)
            # whose requested cursor extends below the current upper window.
            if self.memory.story.header.version not in LATE_SCREEN_VERSIONS:
                raise ExecutionError("Cursor is outside the upper window")
            self.split(min(row, self.height))
        self._cursor(row, column)
        self.command("at", row, column)

    def font(self, number: int) -> int:
        """Choose a supported font for the current window, or query with zero."""
        if number not in (0, 1, 4):
            return 0
        fonts = list(self.state.fonts)
        previous = fonts[self.state.window]
        if number:
            fonts[self.state.window] = number
            self.state = replace(self.state, fonts=tuple(fonts))
            self.command("font", number)
        return previous

    def style(self, style: int) -> None:
        """Activate style bits, or clear them all with Roman (zero)."""
        if not 0 <= style <= 15:
            raise ExecutionError("Invalid text style")
        styles = list(self.state.styles)
        styles[self.state.window] = styles[self.state.window] | style if style else 0
        self.state = replace(self.state, styles=tuple(styles))
        if not style:
            self.command("normal")
        for bit, name in ((1, "invert"), (2, "bold"), (4, "italic"), (8, "fixed")):
            if style & bit:
                self.command(name)

    def colour(self, foreground: int, background: int, *, true: bool = False) -> None:
        """Resolve default/current colours and record the selected colour pair."""
        pair = list(self.state.colours[self.state.window])
        for i, value in enumerate((foreground, background)):
            if value == (-2 if true else 0):
                continue
            if value == (-1 if true else 1):
                pair[i] = ("white", "black")[i]
            elif true and 0 <= value <= 0x7FFF:
                components = [(value >> shift) & 31 for shift in (0, 5, 10)]
                pair[i] = "#" + "".join(f"{(c << 3) | (c >> 2):02x}" for c in components)
            elif not true and 2 <= value <= 12:
                pair[i] = COLOURS[value - 2]
            else:
                raise ExecutionError("Unsupported text colour")
        colours = list(self.state.colours)
        colours[self.state.window] = tuple(pair)
        self.state = replace(self.state, colours=tuple(colours))
        # Preserve operand intent for theme-aware consumers while keeping the
        # VM's resolved colour state and checkpoints unchanged.
        tokens = [
            "current"
            if value == (-2 if true else 0)
            else "default"
            if value == (-1 if true else 1)
            else pair[i]
            for i, value in enumerate((foreground, background))
        ]
        self.command("color", *tokens)

    def buffer(self, enabled: int) -> None:
        """Record the lower window's buffering policy, irrespective of selection."""
        if enabled not in (0, 1):
            raise ExecutionError("Invalid output buffering mode")
        self.state = replace(self.state, buffered=bool(enabled))
        self.command("buffer", "on" if enabled else "off")

    def erase_line(self, value: int) -> None:
        """Clear from the upper cursor to the right edge, without moving it."""
        if value == 1 and self.state.window == 1:
            self.command("clear-line")

    def erase(self, window: int) -> None:
        """Reset the specified logical window, preserving the emitted transcript."""
        if window not in (-2, -1, 0, 1):
            raise ExecutionError(f"Invalid window to erase: {window}")
        if window == -1:
            bottom = self.height if self.memory.story.header.version == 4 else 1
            self.state = replace(self.state, window=0, split_lines=0, cursors=((bottom, 1), (1, 1)))
            self.command("clear", "all")
            self.command("split", 0)
            self.command("bottom")
            self._cursor_command(0)
            self._cursor_command(1)
        elif window == -2:
            self.command("clear", "all")
        else:
            cursors = list(self.state.cursors)
            row = 1
            if window == 0:
                row = (
                    self.height
                    if self.memory.story.header.version == 4
                    else min(self.height, self.state.split_lines + 1)
                )
            cursors[window] = (row, 1)
            self.state = replace(self.state, cursors=tuple(cursors))
            self.command("clear", "top" if window else "bottom")
            self._cursor_command(window)
