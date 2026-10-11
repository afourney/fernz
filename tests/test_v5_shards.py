"""Every comprehensive V5 case and archive belongs to exactly one CI group."""

import pytest

from .v5_corpus import GAMES
from .v5_shards import selected_games


@pytest.mark.parametrize("total", (1, 2, 3, 33))
def test_v5_shards_partition_the_complete_corpus(total):
    groups = [selected_games(f"{part}/{total}") for part in range(1, total + 1)]
    assert all(groups)
    selected = [game for group in groups for game in group]
    assert len(selected) == len(set(selected)) == len(GAMES)
    assert set(selected) == set(selected_games())


@pytest.mark.parametrize("shard", ("0/3", "4/3", "1/34", "one", "1/2/3"))
def test_v5_shards_reject_invalid_selectors(shard):
    with pytest.raises(ValueError, match="V5 shard"):
        selected_games(shard)
