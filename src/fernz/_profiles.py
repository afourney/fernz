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
    score_global: int = 1
    moves_global: int = 2
    score_byte: bool = False
    score_signed: bool = True
    loss_hashes: frozenset[str] = frozenset()
    victory_hashes: frozenset[str] = frozenset()

    def outcomes(self, observation: str) -> tuple[bool, bool]:
        """Classify the latest response, tolerating differences in whitespace."""
        lines = {" ".join(line.split()) for line in observation.splitlines()}
        hashes = {sha256(line.encode()).hexdigest() for line in lines}
        # A text host can retain the final input prompt after an outcome line.
        final_line = observation.splitlines()[-1] if observation else ""
        if final_line.endswith(">"):
            hashes.add(sha256(" ".join(final_line[:-1].split()).encode()).hexdigest())
        return (
            bool(lines & self.loss_lines or hashes & self.loss_hashes),
            bool(lines & self.victory_lines or hashes & self.victory_hashes),
        )


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


# Retained V3 profiles measured through public API calls; see docs/V3_GAMES.md.
_PROFILES.update(
    {
        # ballyhoo.z3
        "05e6558febc163cb6e6ea6fb0d2af3a9238fe8cb1360a9245c3e81ff01da0b44": StoryProfile(
            max_score=200,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            player_object=211,
            score_global=1,
            score_byte=True,
            score_signed=False,
            moves_global=2,
            loss_hashes=frozenset(
                ["79142cf0dd371dacbe26821cab12d22015ea04eb4b095988b65dd0524b77d1a6"]
            ),
            victory_hashes=frozenset(
                ["3629bf4f8dfd661de042538f255b146504726d33e8c8f054c29f0400f6590425"]
            ),
        ),
        # cutthroat.z3
        "33cb5281443395123b884500124c706ba27144fe1375a82e56fe37b51e2f4bd7": StoryProfile(
            max_score=250,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            player_object=184,
            score_global=115,
            score_byte=True,
            score_signed=False,
            moves_global=2,
            loss_hashes=frozenset(
                ["20c3a1559d63bab1c7864b6942a4df7daae81773995d1b2bf1d80ba6cdd3f9ee"]
            ),
            victory_hashes=frozenset(
                ["35faf39f08173dccae5cc2553a8d7ee71499a17333bcc9e637af67ea3214a016"]
            ),
        ),
        # enchanter.z3
        "78645d1fa00856e14eb452f7b54ea2954b329cd77bf3852fd511797c29a1be5d": StoryProfile(
            max_score=400,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            player_object=55,
            score_global=1,
            score_byte=False,
            score_signed=True,
            moves_global=2,
            loss_hashes=frozenset(
                ["d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6"]
            ),
            victory_hashes=frozenset(
                ["be5839aa96530c2a49c0d492fb89cc7f51b1ab529ddd94f213ee2ee343b7a8d7"]
            ),
        ),
        # hhgg.z3
        "88464cdf4e56fbf9e7fe7da0cb011b2ee834ba20caa7bded44005787a70b3928": StoryProfile(
            max_score=400,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            player_object=31,
            score_global=1,
            score_byte=False,
            score_signed=True,
            moves_global=2,
            loss_hashes=frozenset(
                ["f57749700aa5580c1872ba450147038cc991d92fdd8224303de1d45ead1d35a8"]
            ),
            victory_hashes=frozenset(
                ["1d3c8bcf2ba9c3b0fce6a72cbdbc31d876b7a88f3a71cc4e33d3d6602c829ab4"]
            ),
        ),
        # hollywood.z3
        "76dee4f03b68d700b5e0f0282b9f8e512ae347baea92994bb2ba5c6650d3ede5": StoryProfile(
            max_score=150,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            player_object=50,
            score_global=1,
            score_byte=True,
            score_signed=False,
            moves_global=2,
            loss_hashes=frozenset(
                ["2f66991596a548f4eca0142c9e55936ab4181b45fcf29f336b102d0fe5869772"]
            ),
            victory_hashes=frozenset(
                ["66ae2eb3064dbe229b75b2315b66c1d5a525c3f211d07186344c32ef46603c87"]
            ),
        ),
        # infidel.z3
        "9bdb37a4647c1614df44289e4237730b6b3bc3daf46d34201738fe68f15eb410": StoryProfile(
            max_score=400,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            player_object=223,
            score_global=1,
            score_byte=False,
            score_signed=True,
            moves_global=2,
            loss_hashes=frozenset(
                ["d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6"]
            ),
            victory_hashes=frozenset(
                ["1667d5b9a1a19f510c24b69e77029576944ccd90d645662a4881da6cf5f6457a"]
            ),
        ),
        # lurking.z3
        "79f06726be1683509501ec0d31415baa9789b2ff2a4c9993659de2bc21e6bfd7": StoryProfile(
            max_score=100,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            player_object=56,
            score_global=1,
            score_byte=True,
            score_signed=False,
            moves_global=2,
            loss_hashes=frozenset(
                ["d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6"]
            ),
            victory_hashes=frozenset(
                ["93f28264196b9ecce5e0cdcce061184fd2f3c8046a6eb994a329ae6ae5c0f90e"]
            ),
        ),
        # planetfall.z3
        "495239678b48cf1b7f2662e4aca2f5412064a9d1ec782f1d2977324dfabd7926": StoryProfile(
            max_score=80,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            player_object=236,
            score_global=1,
            score_byte=True,
            score_signed=False,
            moves_global=225,
            loss_hashes=frozenset(
                ["d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6"]
            ),
            victory_hashes=frozenset(
                ["87e5056215931ffa11dadabbced1df3067dc93050f0e81113caca5036d4d925d"]
            ),
        ),
        # plundered.z3
        "e388ff26a8fce667bb055cbdfa1003b7d9375d251baff7760edc35772b1ff111": StoryProfile(
            max_score=25,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            player_object=192,
            score_global=1,
            score_byte=True,
            score_signed=False,
            moves_global=2,
            loss_hashes=frozenset(
                ["d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129"]
            ),
            victory_hashes=frozenset(
                ["f9a87616b657634da92d48a85f9986e515489c9d308e862a19fc73c7c515f9ae"]
            ),
        ),
        # seastalker.z3
        "027836f768d1607f7769f506b438a9058afed1836e69da34268fe70a229e6e5a": StoryProfile(
            max_score=100,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            player_object=191,
            score_global=1,
            score_byte=True,
            score_signed=True,
            moves_global=2,
            loss_hashes=frozenset(
                ["49d8b8e031509f3d15f919f0ca35ca4144137ccc8089579abcd6b8771eed7df0"]
            ),
            victory_hashes=frozenset(
                ["e68decd238f38bc806433a0bdd4faa2476c175d1f9add8625b3ad006bd1d3f4c"]
            ),
        ),
        # sorcerer.z3
        "f7e1030b54059826196354ff3af09f69b3884af3ee55bd471ea5586e826ba5bf": StoryProfile(
            max_score=400,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            player_object=223,
            score_global=1,
            score_byte=False,
            score_signed=True,
            moves_global=2,
            loss_hashes=frozenset(
                ["d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6"]
            ),
            victory_hashes=frozenset(
                ["7e1b8729ffaa149f9e5772c49107ab0fc83fa791919263ec8f8c70e32ffa1ac3"]
            ),
        ),
        # spellbrkr.z3
        "7680fe943cb2cea2ff2faf47cac6fcd38212e9d8e3652a51da9a6fd69a79870a": StoryProfile(
            max_score=600,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            player_object=52,
            score_global=1,
            score_byte=False,
            score_signed=True,
            moves_global=2,
            loss_hashes=frozenset(
                ["d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6"]
            ),
            victory_hashes=frozenset(
                ["ab0ca79a773d9aef10f6815546b486baafc5da9c1d0968493f3765c340737ebc"]
            ),
        ),
        # wishbringer.z3
        "b7c23d545903cd6b8ce51c4b3fa76dd6cfddfbdc992960fa2c527363e844f2a7": StoryProfile(
            max_score=100,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            player_object=238,
            score_global=136,
            score_byte=True,
            score_signed=False,
            moves_global=135,
            loss_hashes=frozenset(
                ["bd2f48c174187b83cdab277d5aca1ed0213be1396a558be6e420675d38c64b56"]
            ),
            victory_hashes=frozenset(
                ["017a57d02440a16b01f835f0fd458b5a6445762c50ff2526a8e7ea3887c9e438"]
            ),
        ),
        # zork2.z5
        "39e3a8bda879e9296ac05c8bdcdae12a1a6fb447a1ef531838e82cfa2db210ac": StoryProfile(
            max_score=400,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            player_object=4,
            score_global=1,
            score_byte=False,
            score_signed=True,
            moves_global=2,
            loss_hashes=frozenset(
                ["d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6"]
            ),
            victory_hashes=frozenset(
                ["ef32f630e46503230614d2af42d706a13dc5e34b239eb01327e8ad42264e143a"]
            ),
        ),
        # zork3.z5
        "62ced461c650265ea55b17e7f0e368724e0b43bf92af6f1a3d566e82c7608be2": StoryProfile(
            max_score=7,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            player_object=202,
            score_global=1,
            score_byte=True,
            score_signed=False,
            moves_global=2,
            loss_hashes=frozenset(
                ["d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6"]
            ),
            victory_hashes=frozenset(
                ["6f8bf4aa778f3c80135b4930908046b325b5e91377af4c32e2b3d77b635e2033"]
            ),
        ),
    }
)
