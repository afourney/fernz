"""Shared scenarios for live reference comparisons and recorded-vector generation."""

from dataclasses import dataclass

ZORK1_SHA256 = "0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd"
WALKTHROUGH_SEED = 12


@dataclass(frozen=True)
class Scenario:
    checkpoint: str
    actions: tuple[str, ...]
    id: str


# Prefix lengths from the public walkthrough, with independently observed rooms.
# Include outdoor, indoor, underground, container, vehicle, and late-game states.
CHECKPOINTS = {
    "west-house": (0, 180),
    "tree": (3, 88),
    "window": (8, 79),
    "living-room": (12, 193),
    "kitchen": (20, 203),
    "torch-room": (35, 105),
    "dam-lobby": (100, 154),
    "beach": (214, 33),
    "boat": (218, 156),
    "drafty-room": (350, 228),
    "full-score": (387, 193),
}

COMMAND_GROUPS = {
    "unknown-verb": ("glorb", "xyzzy", "frobnicate mailbox", "teleport kitchen"),
    "unknown-noun": (
        "take flibbertigibbet",
        "open flibbertigibbet",
        "examine flibbertigibbet",
        "put flibbertigibbet in mailbox",
        "put lamp in flibbertigibbet",
    ),
    "absent-object": (
        "take grue",
        "open rainbow",
        "read troll",
        "attack thief with sword",
        "give leaflet to troll",
        "unlock door with key",
    ),
    "red-herring": (
        "kick door",
        "knock on door",
        "kick mailbox",
        "take house",
        "take mailbox",
        "eat mailbox",
        "drink lamp",
        "read sword",
        "smell leaflet",
        "listen",
        "sing",
        "pray",
        "wave sword",
        "rub lamp",
        "climb house",
    ),
    "object-operation": (
        "open mailbox",
        "close mailbox",
        "take all",
        "drop all",
        "take all except lamp",
        "put lamp in mailbox",
        "put lamp in lamp",
        "put lamp on table",
        "turn on lamp",
        "turn off lamp",
        "move rug",
        "open trap door",
        "enter boat",
        "exit boat",
    ),
    "incomplete": ("take", "open", "put", "give", "attack", "put lamp", "look under"),
    "pronoun": ("take it", "drop it", "examine it", "again", "g", "oops mailbox"),
    "lexical": (
        "",
        "   ",
        "LoOk",
        "  OPEN   MAILBOX  ",
        "take leaflets",
        "inventoryyyyy",
        ".",
        ",",
        "!",
        "look!",
        "look;inventory",
        "look,look",
        '"hello"',
        "12345",
        "look. inventory",
        "open mailbox then read leaflet",
        "take lamp and sword",
        "take lamp, sword",
    ),
    "navigation": ("north", "up", "down", "in", "out"),
    "status": ("look", "inventory", "score", "diagnose", "wait"),
}
SCENARIOS = (
    Scenario(
        "living-room",
        ("move rug", "open door", "wooden", "open door", "trap", "look"),
        id="ambiguous-doors-and-clarification",
    ),
    Scenario(
        "west-house",
        ("open", "mailbox", "take", "leaflet", "read it", "drop it", "take it"),
        id="clarification-and-pronouns",
    ),
    Scenario(
        "west-house",
        ("glorb", "open flibbertigibbet", "open mailbox", "take leaflet", "read leaflet"),
        id="recover-after-unknown-words",
    ),
    Scenario(
        "west-house",
        ("enter door", "look", "open mailbox", "take leaflet", "inventory", "north"),
        id="zero-object-jin-and-continued-play",
    ),
    Scenario(
        "west-house",
        (
            "take leaflet",
            "open mailbox",
            "take leaflet",
            "put leaflet",
            "mailbox",
            "close mailbox",
            "take leaflet",
            "open mailbox",
            "take leaflet",
        ),
        id="container-state",
    ),
    Scenario(
        "west-house",
        (
            "kick door",
            "again",
            "knock on door",
            "open door",
            "north",
            "east",
            "open window",
            "enter window",
        ),
        id="futile-door-then-window",
    ),
    Scenario(
        "west-house",
        (
            "look. inventory",
            "open mailbox then take leaflet",
            "read it",
            "drop leaflet and sword",
            "take all",
            "inventory",
        ),
        id="multiple-commands-and-objects",
    ),
    Scenario(
        "west-house",
        (
            "take it",
            "open mailbox",
            "take leaflet",
            "examine it",
            "drop it",
            "g",
            "take it",
            "read it",
        ),
        id="repeat-and-pronoun-history",
    ),
    Scenario(
        "tree",
        ("take nest", "open egg", "drop nest", "down", "take nest", "up", "look in nest"),
        id="tree-detour",
    ),
    Scenario(
        "window",
        (
            "close window",
            "enter window",
            "open window",
            "enter window",
            "close window",
            "west",
            "east",
        ),
        id="window-state-and-navigation",
    ),
    Scenario(
        "living-room",
        (
            "take all",
            "open case",
            "put sword in case",
            "close case",
            "take sword",
            "open case",
            "take sword",
            "move rug",
            "open trap door",
            "down",
            "up",
        ),
        id="case-and-trap-door",
    ),
    Scenario(
        "kitchen",
        (
            "take all",
            "open bottle",
            "drink water",
            "drink water",
            "eat lunch",
            "eat lunch",
            "drop all",
            "take all",
        ),
        id="consumables-and-missing-objects",
    ),
    Scenario(
        "torch-room",
        ("look", "turn off lamp", "wait", "turn on lamp", "take torch", "drop torch", "take torch"),
        id="light-and-time",
    ),
    Scenario(
        "dam-lobby",
        (
            "read guidebook",
            "take all",
            "read guidebook",
            "drop guidebook",
            "north",
            "south",
            "wait",
            "diagnose",
        ),
        id="dam-exploration",
    ),
    Scenario(
        "beach",
        ("read label", "enter boat", "look", "take boat", "exit boat", "take boat", "drop boat"),
        id="vehicle-entry-exit",
    ),
    Scenario(
        "boat",
        ("inventory", "take boat", "enter boat", "exit boat", "enter boat", "look", "wait"),
        id="already-in-vehicle",
    ),
    Scenario(
        "drafty-room",
        (
            "look in basket",
            "take diamond",
            "put diamond in basket",
            "put lamp in basket",
            "take lamp",
            "wait",
        ),
        id="late-game-container",
    ),
    Scenario(
        "full-score",
        ("score", "take all from case", "score", "put all in case", "score", "wait", "look"),
        id="treasures-and-score-changes",
    ),
    Scenario(
        "west-house",
        ("south", "east", "east", "east", "jump", "look", "inventory", "wait"),
        id="recoverable-death-and-continuation",
    ),
)

COMBAT_ACTIONS = (
    "kick door",
    "north",
    "east",
    "open window",
    "enter window",
    "west",
    "take sword",
    "take lamp",
    "turn on lamp",
    "move rug",
    "open trap door",
    "down",
    "north",
    "attack troll with leaflet",
    "attack troll with sword",
    "attack troll with sword",
    "attack troll with sword",
    "south",
    "diagnose",
    "inventory",
    "wait",
    "look",
)

COMBAT_SEEDS = (1, 12, 42, 1000, 32767)
CELLAR_DEATH_ACTIONS = (
    "take lamp",
    "turn on lamp",
    "move rug",
    "open trap door",
    "down",
    "south",
    "jump",
    "look",
    "inventory",
    "wait",
)
