"""Immutable observations and the version-one display stream vocabulary."""

from dataclasses import dataclass
from typing import ClassVar

COLOURS = (
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
    "light-grey",
    "medium-grey",
    "dark-grey",
)


@dataclass(frozen=True, slots=True)
class ScreenOutputClipped:
    """Cell painting outside the logical screen during one execution boundary.

    Coordinates are one-based. Spaces count as painting, including quote-box
    backgrounds. The transcript retains the text even when screen cells do not.
    """

    code: ClassVar[str] = "screen_output_clipped"
    width: int
    height: int
    window: int
    clipped_cells: int
    min_row: int
    max_row: int
    min_column: int
    max_column: int


@dataclass(frozen=True, slots=True)
class Observation:
    """Output emitted during one reset or step, rather than a screen snapshot.

    ``stream`` interleaves escaped story text and display commands in execution
    order. A literal less-than sign is doubled (``<<``). ``text`` contains the
    plain transcript of both windows, with recognized story prompts omitted.
    Clearing or overwriting the display never removes previously emitted text.
    """

    stream: str
    text: str
    diagnostics: tuple[ScreenOutputClipped, ...] = ()
