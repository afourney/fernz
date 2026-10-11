"""Partition comprehensive V5 checks by approximate object-inspection work."""

from .v5_corpus import GAMES
from .v5_walkthrough_cases import GAMES as WALKTHROUGHS


def selected_games(shard=None):
    if shard is None:
        return GAMES
    try:
        part, total = map(int, shard.split("/"))
    except (ValueError, AttributeError) as error:
        raise ValueError("Use a V5 shard such as 1/3") from error
    if not 1 <= part <= total <= len(GAMES):
        raise ValueError("V5 shard must satisfy 1 <= part <= total <= 33")
    # Existing trajectory suites also include detours and per-turn replay.
    weights = {"905": 50_000, "balances": 100_000, "sherlock": 350_000}
    weights.update({name: case["length"] * case["objects"] for name, case in WALKTHROUGHS.items()})
    groups, costs = [[] for _ in range(total)], [0] * total
    for game in sorted(GAMES, key=lambda name: (-weights[name], name)):
        index = min(range(total), key=lambda n: (costs[n], n))
        groups[index].append(game)
        costs[index] += weights[game]
    return tuple(sorted(groups[part - 1]))
