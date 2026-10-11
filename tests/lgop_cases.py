"""LGOP's measured build and input sequences; see docs/LGOP.md for provenance."""

import json
from pathlib import Path

from .v3_cases import COMMANDS as COMMON_COMMANDS

SEED = 42
PLAYER = 199
STORY = {
    "filename": "lgop.z3",
    "version": 3,
    "release": 160,
    "serial": "860521",
    "file_sha256": "7420823ac2ba15170895e411964f69e527c92beb07a7815a7a02d120eb75983d",
    "player": PLAYER,
    "max_score": None,
    "world_count": 228,
}
# Ordinary command prompts, outside acknowledgement or clarification reads.
CHECKPOINTS = (1, 100, 190, 283, 350)
COMMANDS = (
    *COMMON_COMMANDS,
    "examine me",
    "ask trent about goddesses",
    "ask tiffany about goddesses",
    "drop flashlight",
    "take flashlight",
    "read comic book",
    "enter circle",
    "wear suit",
    "clap",
    "say kweepa",
)
LOSS_HASH = "f57749700aa5580c1872ba450147038cc991d92fdd8224303de1d45ead1d35a8"
WIN_HASH = "49a3ccecfd64b3cc402fdb5232544cc9887b7578f5c7230dbbc6ab2054cdf590"


def archive_path():
    return Path(__file__).parent / "vectors" / "lgop_vectors.zip"


def walkthrough():
    return json.loads((Path(__file__).parent / "routes" / "lgop.json").read_text())


def female_route(length=30):
    actions = walkthrough()[:length]
    actions[1] = "ne"
    actions[6] = "sw"
    return [
        action.replace("trent", "tiffany")
        .replace("thorbast", "thorbala")
        .replace("his sword", "her sword")
        .replace("woman", "man")
        .replace("female gorilla", "male gorilla")
        for action in actions
    ]


def partial_routes():
    return (
        ("tiffany-opening", 42, female_route()),
        ("tiffany-body-swap", 42, female_route(108)),
        (
            "tiffany-inventory",
            42,
            [
                *female_route()[:22],
                "inventory",
                "drop flashlight",
                "inventory",
                "take flashlight",
                "inventory",
            ],
        ),
        *((f"seed-{seed}", seed, walkthrough()[:30]) for seed in (1, 1000)),
        *((f"tiffany-seed-{seed}", seed, female_route()) for seed in (1, 1000)),
        ("opening-loss", 42, ["", *("wait",) * 4, "look", "inventory"]),
        (
            "tiffany-prison",
            42,
            [
                *female_route()[:17],
                "kick door",
                "glorb",
                "take unicorn",
                "ask tiffany about goddesses",
                "look",
                "inventory",
            ],
        ),
    )
