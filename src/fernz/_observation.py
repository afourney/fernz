"""Immutable observations and the version-one display stream vocabulary."""

from dataclasses import dataclass

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
class Observation:
    """Output emitted during one reset or step, rather than a screen snapshot.

    ``stream`` interleaves escaped story text and display commands in execution
    order. A literal less-than sign is doubled (``<<``). ``text`` contains the
    plain transcript of both windows, with recognized story prompts omitted.
    Clearing or overwriting the display never removes previously emitted text.
    """

    stream: str
    text: str
