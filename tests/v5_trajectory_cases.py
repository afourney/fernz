"""Full V5 trajectory cases pinned to independently measured story profiles."""

GAMES = {
    "balances": {
        "length": 122,
        "player": 20,
        "max_score": 51,
        "winning_score": 50,
        "score_global": 1,
        "moves_global": 2,
        "checkpoints": (0, 14, 44, 87, 114, 122),
    },
    "sherlock": {
        "length": 339,
        "player": 232,
        "max_score": 100,
        "winning_score": 100,
        "score_global": 27,
        "moves_global": 159,
        "checkpoints": (0, 14, 44, 138, 243, 318, 325, 339),
    },
}
SEED = 0
COMMANDS = (
    "look",
    "inventory",
    "wait",
    "flibbertigibbet",
    "take unicorn",
    "open unicorn",
    "kick door",
    "examine me",
    "drop all",
    "north",
    "south",
    "east",
    "west",
    "score",
)
GAME_COMMANDS = {
    "balances": ("learn rezrov", "rezrov me", "examine grimoire", "jump", "sit on carpet"),
    "sherlock": ("ask holmes about jewels", "blow whistle", "enter cab", "examine hat", "jump"),
}
DEATHS = {"balances": (44, ("jump",)), "sherlock": (318, ("wait for 48 hours",))}
PERSISTENCE_TURN = {"balances": 14, "sherlock": 44}
