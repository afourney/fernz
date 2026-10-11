"""Story-specific metadata measured through public reference behavior.

Keep game conventions outside opcode execution. Profiles identify the original
addressable story image, so renaming or padding a file does not change support.
"""

from dataclasses import dataclass
from hashlib import sha256

from ._story import Story


@dataclass(frozen=True, slots=True)
class StoryProfile:
    """A score limit, outcome response lines, and optional known player object."""

    max_score: int
    loss_lines: frozenset[str]
    victory_lines: frozenset[str]
    player_object: int | None = None

    def outcomes(self, observation: str) -> tuple[bool, bool]:
        """Classify the latest response, tolerating differences in whitespace."""
        lines = {" ".join(line.split()) for line in observation.splitlines()}
        return bool(lines & self.loss_lines), bool(lines & self.victory_lines)


# Zork I release 88, serial 840726. See docs/STORY_QUERIES.md for the
# independent black-box evidence and the limits of response-based outcomes.
_PROFILES = {
    "158f1f63b1302591bbce30e1ec23b17909d2a66e39403ed14593a75280b1e7f9": StoryProfile(
        max_score=350,
        loss_lines=frozenset({"**** You have died ****"}),
        victory_lines=frozenset({"Inside the Barrow"}),
        player_object=4,
    ),
}


def profile_for(story: Story) -> StoryProfile | None:
    """Return metadata only for an independently verified story image."""
    digest = sha256(story.data[: story.size]).hexdigest()
    return _PROFILES.get(digest)
