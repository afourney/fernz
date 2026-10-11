"""Measured public-reference presentation rules for the retained V5 routes.

Only comparison projections are changed. Fernz's full text and display stream
retain punctuation, literal greater-than signs and all upper-window output.
See docs/V5.md for the measurements and limits of this reference channel.
"""

import re

from .v5_walkthrough_cases import GAMES


def normalize(text):
    """Ignore physical whitespace while retaining punctuation and word order."""
    return " ".join(text.replace("\r\n", "\n").split()).removeprefix("> ").removesuffix(" >")


def reference_text(text, game, turn):
    """Remove the reference's known post-quit diagnostic at one terminal boundary."""
    if game == "murdac" and turn == GAMES[game]["length"]:
        suffix = "*** Invalid Meaning_LX value at action time **"
        assert text.endswith(suffix)
        text = text[: -len(suffix)]
    return normalize(text)


def fernz_text(observation, game, turn):
    """Project the complete ordered transcript onto the reference's visible text."""
    text = observation.text
    if turn == 0:
        text = text[1:]  # Public reset clips one character, including Spirit's title.
    if game == "acorncourt":
        prompt = re.search(r"\n\n\[[^\n]+\]>", text)
        if prompt:
            text = text[: prompt.start()]
            text = re.sub(
                r"\n\n\[Your score has just gone up by (?:ten|twenty) points\.\]$", "", text
            )
    elif game == "loose" and turn == GAMES[game]["length"]:
        pass  # The reference keeps this winning prompt and its upper scoreboard.
    elif game == "detective":
        # >> is part of this story's room headings, including the status line
        # after its prompt. Only the prompt at the start of a line is clipped.
        prompt = re.search(r"\n> ?", text)
        if prompt:
            trim = 0 if turn == GAMES[game]["length"] else 1
            text = text[: max(0, prompt.start() - trim)]
    elif ">" in text:
        # Most measured profiles clip two characters before the first >,
        # even inside artwork or code. Detective preserves its >> room titles.
        end = text.index(">")
        trim = 1 if game == "weapon" and turn == GAMES[game]["length"] else 2
        text = text[: max(0, end - trim)]
    return normalize(text)
