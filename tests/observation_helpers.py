"""Explicit transcript adapters and an independent display-stream reader."""

from fernz import Observation


def plain_text(observation):
    """Select Fernz's public transcript; public reference APIs already return text."""
    if isinstance(observation, Observation):
        return observation.text
    assert isinstance(observation, str)
    return observation


def text_response(response):
    """Compare transcript and return metadata independently of display commands."""
    return (plain_text(response[0]), *response[1:])


def stream_events(stream):
    """Parse the documented grammar without using interpreter output helpers."""
    i = 0
    text = []
    while i < len(stream):
        if stream.startswith("<<", i):
            text.append("<")
            i += 2
        elif stream[i] == "<":
            if text:
                yield "text", "".join(text)
                text.clear()
            end = stream.index(">", i + 1)
            token = stream[i + 1 : end]
            assert "<" not in token
            yield "command", token.split()
            i = end + 1
        else:
            text.append(stream[i])
            i += 1
    if text:
        yield "text", "".join(text)


def window_text(observation, selected=0, *, initial_window=0, minimum_split=0):
    """Read one window's emitted text from the public stream, never private hooks."""
    assert isinstance(observation, Observation)
    window = initial_window
    split = 0
    parts = []
    for kind, value in stream_events(observation.stream):
        if kind == "text":
            if window == selected and split >= minimum_split:
                parts.append(value)
        elif value[0] in ("reset", "bottom"):
            window = 0
        elif value[0] == "top":
            window = 1
        elif value[0] == "split":
            split = int(value[1])
        elif (
            value[0] == "at"
            and minimum_split
            and window == selected
            and split >= minimum_split
            and (len(value) == 3 or value[3] == ("top" if selected else "bottom"))
        ):
            parts.append(" ")
    return "".join(parts)


def join_observations(first, second):
    return Observation(first.stream + second.stream, first.text + second.text)
