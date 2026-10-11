"""Story-specific metadata measured through public reference behavior.

Keep game metadata and narrowly measured legacy quirks together. Profiles identify
the original addressable image, so renaming or padding does not change support.
"""

from dataclasses import dataclass
from hashlib import sha256

from ._story import Story


@dataclass(frozen=True, slots=True)
class StoryProfile:
    """Measured query metadata and bounded quirks for an exact story image."""

    max_score: int | None
    loss_lines: frozenset[str]
    victory_lines: frozenset[str]
    player_object: int | None = None
    score_global: int = 1
    moves_global: int = 2
    score_byte: bool = False
    score_signed: bool = True
    score_negated: bool = False
    loss_hashes: frozenset[str] = frozenset()
    victory_hashes: frozenset[str] = frozenset()
    moves_offset: int = 0
    moves_byte: bool = False
    victory_score: int | None = None
    victory_overrides_loss: bool = False
    ignored_attribute_writes: frozenset[int] = frozenset()
    unordered_inspection_objects: frozenset[int] = frozenset()
    strip_command_prompt: bool = False

    def outcomes(self, observation: str) -> tuple[bool, bool]:
        """Classify the latest response, tolerating differences in whitespace."""
        lines = {" ".join(line.split()) for line in observation.splitlines()}
        hashes = {sha256(line.encode()).hexdigest() for line in lines}
        # A text host can retain the final input prompt after an outcome line.
        final_line = observation.splitlines()[-1] if observation else ""
        if final_line.endswith(">"):
            hashes.add(sha256(" ".join(final_line[:-1].split()).encode()).hexdigest())
        loss = bool(lines & self.loss_lines or hashes & self.loss_hashes)
        victory = bool(lines & self.victory_lines or hashes & self.victory_hashes)
        if self.victory_overrides_loss and victory:
            loss = False
        return loss, victory


# Zork I release 88, serial 840726. See docs/STORY_QUERIES.md for the
# independent black-box evidence and the limits of response-based outcomes.
_PROFILES = {
    # LGOP release 160, serial 860521. Public execution and snapshot probes;
    # randomized scoring has no fixed maximum. See docs/LGOP.md.
    "7420823ac2ba15170895e411964f69e527c92beb07a7815a7a02d120eb75983d": StoryProfile(
        max_score=None,
        player_object=199,
        loss_lines=frozenset(),
        victory_lines=frozenset(),
        loss_hashes=frozenset({"f57749700aa5580c1872ba450147038cc991d92fdd8224303de1d45ead1d35a8"}),
        victory_hashes=frozenset(
            {"49a3ccecfd64b3cc402fdb5232544cc9887b7578f5c7230dbbc6ab2054cdf590"}
        ),
        victory_overrides_loss=True,
    ),
    # Trinity release 12, serial 860926: public counter-width, object and
    # outcome probes. Its winning menu also sets the reference's loss flag.
    "367a95f056ac7ae00e0f73230c9c3e0e4ab24a06ff775b66cc42765d42491bc0": StoryProfile(
        max_score=100,
        player_object=103,
        score_global=154,
        moves_global=133,
        loss_lines=frozenset(),
        victory_lines=frozenset(),
        loss_hashes=frozenset({"daa295096fdb87c3acc367119e7affa07aae06cb05ceaf6a019faff63e8b9ddf"}),
        victory_hashes=frozenset(
            {"25821b62fa9676a08657a1ebe0b5cd04ef2176806e5a44e72ca020018c2c6c46"}
        ),
        victory_overrides_loss=True,
    ),
    # Balances release 5, serial 961216: public counter and outcome probes.
    "b21a405597b1988ac1726fe143dbd1c9076f27f450885bb8f0080f8e0cac7b2a": StoryProfile(
        max_score=51,
        loss_lines=frozenset(),
        victory_lines=frozenset(),
        player_object=20,
        score_byte=True,
        score_signed=False,
        loss_hashes=frozenset({"d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129"}),
        victory_hashes=frozenset(
            {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
        ),
    ),
    # Sherlock release 21, serial 871214. Attribute 48 writes are a measured
    # historical no-op for this exact image; other invalid attributes fail.
    "d364c24bd518b5691911d2653c4b54986d6bf3f5ce3813192bbabc5c2c318dd2": StoryProfile(
        max_score=100,
        loss_lines=frozenset(),
        victory_lines=frozenset(),
        player_object=232,
        score_global=27,
        moves_global=159,
        score_byte=True,
        score_signed=False,
        loss_hashes=frozenset({"e9133ed4beff567b4a46139d9c8bc8b22dc776bba4bae133b617cf04fc642982"}),
        victory_hashes=frozenset(
            {"1d02bf89405591d860cb6a2e619ed3b47fb4b12971f7f14e3d1faf991c7ce60c"}
        ),
        ignored_attribute_writes=frozenset({48}),
        unordered_inspection_objects=frozenset({308}),
    ),
    "158f1f63b1302591bbce30e1ec23b17909d2a66e39403ed14593a75280b1e7f9": StoryProfile(
        max_score=350,
        loss_lines=frozenset({"**** You have died ****"}),
        victory_lines=frozenset({"Inside the Barrow"}),
        player_object=4,
        strip_command_prompt=True,
    ),
    # 9:05 release 1, serial 120724. Public observations give a response-based
    # score and elapsed minutes from global 17, starting at 9:05 (545 minutes).
    "de23edb34c38ac8e9bf831f33b358d89a9093fcc84941dba0997194786cd1a7d": StoryProfile(
        max_score=1,
        loss_lines=frozenset(),
        victory_lines=frozenset(),
        player_object=28,
        moves_global=17,
        moves_offset=-545,
        victory_score=1,
        loss_hashes=frozenset({"d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129"}),
        victory_hashes=frozenset(
            {"681e54caddcf41c9d8e04f174a7246ce14a2f6b3c8f3a95dc4b255f9eab3f097"}
        ),
    ),
}


def profile_for(story: Story) -> StoryProfile | None:
    """Return metadata only for an independently verified story image."""
    digest = sha256(story.data[: story.size]).hexdigest()
    return _PROFILES.get(digest)


# Exact-image V8 metadata from public API probes; see docs/V8.md.
_PROFILES.update(
    {
        # Afflicted release 1, serial 080906: negate its signed sanitation rating.
        "f68f7686380ba104f638946693dc4e5686edf7ef7a0be239a77f6278043a0967": StoryProfile(
            max_score=75,
            player_object=57,
            score_global=26,
            score_negated=True,
            moves_global=3,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # Anchorhead release 5, serial 990206: its 99-point ending is a victory,
        # although the public reference classifies it as a loss.
        "d2b6b44e96cfdda0f83999d6bc631973721d2e3ed7be910bc7d60f143ce5f34d": StoryProfile(
            max_score=100,
            player_object=20,
            score_global=16,
            score_byte=True,
            score_signed=False,
            moves_global=4,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            loss_hashes=frozenset(
                {"d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129"}
            ),
            victory_hashes=frozenset(
                {"0d16f9bc6f52536416b303975143cfc6f5b8b0d4689be47e784679b32117f65d"}
            ),
        ),
        # Party Foul release 4, serial 100208: one on the winning response.
        "d6fb556faf4a18502719802eaa43fc952f763c4d31f3a7913bd54642f61df6d6": StoryProfile(
            max_score=1,
            player_object=48,
            moves_global=3,
            victory_score=1,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # Yomomma release 3, serial 100228: public counter and ending probes.
        "85070c9147b33d08966dded1b1531248b2a4900a33aced505a84d2938aeff8fc": StoryProfile(
            max_score=35,
            player_object=59,
            score_global=2,
            score_byte=True,
            score_signed=False,
            moves_global=3,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # Lost Pig release 2, serial 080406.
        "e07146727dfe66fb7fe1cef5e8d1e7e403a9cc80465d50f2ca7861a5c266cd56": StoryProfile(
            max_score=7,
            player_object=87,
            score_byte=True,
            score_signed=False,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            loss_hashes=frozenset(
                {"cfa7c3c0abfbfefe551a6fe9adfa3555249a22f740c7ced13cc86d14741d9d8c"}
            ),
            victory_hashes=frozenset(
                {"baa5e6fea220950b5205ecaa513c7609fffd63d77d2c2edc4edf12613da0f83c"}
            ),
            victory_overrides_loss=True,
        ),
        # Snack Time release 1, serial 080929.
        "5dadab996ae847974304dedffefe1f13a99a6cd5d14ea78dacfee4dd60a5d687": StoryProfile(
            max_score=50,
            player_object=44,
            score_global=2,
            moves_global=3,
            score_byte=True,
            score_signed=False,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            victory_hashes=frozenset(
                {"2eef407b5188a23884770c3fdce52ec9ebd4f2d39746c5d773a30db843808105"}
            ),
        ),
    }
)


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


# Remaining retained V5 images; public snapshot/query probes and winning routes.
# See docs/V5.md for counter widths and intentional outcome differences.
_PROFILES.update(
    {
        # acorncourt.z5
        "8e6095022d23bd3f4d984be4a5d91206257b6de707b1260a34242b7eefb90a5d": StoryProfile(
            max_score=30,
            player_object=20,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_byte=True,
            score_signed=False,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {"f6c0646c40fb2fc51984a2ef85eb22134972f8c8d2e778a834b5114410f26a2c"}
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # advent.z5
        "8cf16db63647eb752a294886d6264cd6d5ff3e562480c98dda728d75bebc843d": StoryProfile(
            max_score=350,
            player_object=20,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_global=17,
            moves_global=12,
            victory_overrides_loss=True,
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # adventureland.z5
        "0aa814809ab12f7d4ebe3f81b06522fe5b7caae6354e4aaca2d3696007619286": StoryProfile(
            max_score=100,
            player_object=20,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_byte=True,
            score_signed=False,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129",
                    "d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # awaken.z5
        "1bbd5b4679f2c69f42e12cf3746f580fdf256bc5b4efed01311d7933cbbf1b1b": StoryProfile(
            max_score=50,
            player_object=20,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_global=3,
            score_byte=True,
            score_signed=False,
            moves_global=4,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129",
                    "d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # curses.z5
        "608bfcfd59bd03e82efd2d944ff2f069a8340ab0e2e8f5a6ce68b179551863ba": StoryProfile(
            max_score=550,
            player_object=15,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_global=2,
            moves_global=3,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "0593f62254ab1ba4c08ae1d643013e6e4942512531c1ac45185113460cdc5975",
                    "07ed99552cab0fb52e015f9eb90f75a2c2f2ee9accbafe6d1cfc55e21189a0d3",
                    "14fa2be9ac4fb1e2f5a63a5929070a9a3235a0900ff94066c68e0c004ca0dc5c",
                    "21e736aeb331b6c5c3d0e42e7f7fa73f071f40328b31f9fac5a698ad04294b56",
                    "53e4c00dae50eb9bc7043b906c78a1b9d7f21315005b1c84d689fcf26fbd3c78",
                    "664ffec35974b351d7be2ca1f03decebddf6bd9581982e28af917d1febcaf72d",
                    "839f7a8bff3327cad69b34ca5998f3481be181d9a5570c44fc45dbed649d2452",
                    "83ce00cf2113664b043e2aad373e072043739a9b92ed4f1c1a4c58380dd40ca7",
                    "8c3b6de036e9a295f30bd3a5df9c5ef42fa1bb0c27f09649ba0197d783a7ffdb",
                    "a1b0995061d63aced61496e5445e44c857c3b858ac30715c5ce7639b7bca0ba9",
                    "a321e0ea7e83432189ae2d11e24b88173b1599ff37aec3b0442a42aaed1949a6",
                    "be65d4eba3a771f50a7822f0ef5e4d7003b24a72b76c290c493a681112cfb54b",
                    "cc8df4cb69cf0b2495cfb7b19d8056c5014e685dbdbff5006a39822bf1300db6",
                    "d12e13d22f49290f2e644fce07dfe2cbcda85480a07681258255a5811b97fcf8",
                    "d86b01f7c946960377f3232030e50ee65494287d430a039422120c30a6161991",
                    "e6bf6cc05cb133cdb3e64d42db11f463ca852c728c9fd75e266fcb42be867d03",
                    "f6c0646c40fb2fc51984a2ef85eb22134972f8c8d2e778a834b5114410f26a2c",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # deephome.z5
        "6429e2b7d33d8a1496dae8c090529f43387f0e8915b5699aaffbb23c14e627f4": StoryProfile(
            max_score=300,
            player_object=20,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_global=17,
            moves_global=6,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "a1b0995061d63aced61496e5445e44c857c3b858ac30715c5ce7639b7bca0ba9",
                    "a321e0ea7e83432189ae2d11e24b88173b1599ff37aec3b0442a42aaed1949a6",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # detective.z5
        "fbf3a0c9e566f2322e00af036af3756465c7acdcd73b2dcd34e7ead05d251b3e": StoryProfile(
            max_score=360,
            player_object=90,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_global=14,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129",
                    "d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # dragon.z5
        "358b6afd48a33f5fd7a85b49a77d06d0053e86b17b8f5433cf73758287ffa3f1": StoryProfile(
            max_score=25,
            player_object=20,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "21e736aeb331b6c5c3d0e42e7f7fa73f071f40328b31f9fac5a698ad04294b56",
                    "f6c0646c40fb2fc51984a2ef85eb22134972f8c8d2e778a834b5114410f26a2c",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # enter.z5
        "11bb90ffc213d7aef1c4d5be5fbb8c4861c4d28bcbfa27b9ac58eacef4496ead": StoryProfile(
            max_score=20,
            player_object=20,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_global=6,
            score_byte=True,
            score_signed=False,
            moves_global=7,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "0593f62254ab1ba4c08ae1d643013e6e4942512531c1ac45185113460cdc5975",
                    "07ed99552cab0fb52e015f9eb90f75a2c2f2ee9accbafe6d1cfc55e21189a0d3",
                    "14fa2be9ac4fb1e2f5a63a5929070a9a3235a0900ff94066c68e0c004ca0dc5c",
                    "21e736aeb331b6c5c3d0e42e7f7fa73f071f40328b31f9fac5a698ad04294b56",
                    "53e4c00dae50eb9bc7043b906c78a1b9d7f21315005b1c84d689fcf26fbd3c78",
                    "664ffec35974b351d7be2ca1f03decebddf6bd9581982e28af917d1febcaf72d",
                    "839f7a8bff3327cad69b34ca5998f3481be181d9a5570c44fc45dbed649d2452",
                    "83ce00cf2113664b043e2aad373e072043739a9b92ed4f1c1a4c58380dd40ca7",
                    "8c3b6de036e9a295f30bd3a5df9c5ef42fa1bb0c27f09649ba0197d783a7ffdb",
                    "a1b0995061d63aced61496e5445e44c857c3b858ac30715c5ce7639b7bca0ba9",
                    "a321e0ea7e83432189ae2d11e24b88173b1599ff37aec3b0442a42aaed1949a6",
                    "be65d4eba3a771f50a7822f0ef5e4d7003b24a72b76c290c493a681112cfb54b",
                    "cc8df4cb69cf0b2495cfb7b19d8056c5014e685dbdbff5006a39822bf1300db6",
                    "d12e13d22f49290f2e644fce07dfe2cbcda85480a07681258255a5811b97fcf8",
                    "d86b01f7c946960377f3232030e50ee65494287d430a039422120c30a6161991",
                    "e6bf6cc05cb133cdb3e64d42db11f463ca852c728c9fd75e266fcb42be867d03",
                    "f6c0646c40fb2fc51984a2ef85eb22134972f8c8d2e778a834b5114410f26a2c",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # gold.z5
        "d210d9e769e42eeecc501d7fabd9d91208ca16caa6bfce8392e2e4e8cff2ec56": StoryProfile(
            max_score=100,
            player_object=85,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_byte=True,
            score_signed=False,
            moves_global=12,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "274bc7b5ae62d4554054a8c976e369a7c817170191cff071feecf8154cfb2743",
                    "ae1a73bfe946153367cd2d442e3f9a33fea56dbdf6996021e74c8f1389285c61",
                }
            ),
            victory_hashes=frozenset(
                {"e47fa5a041d13cf5edebb59377b1a6c74cfd3af49bcac4e399b1eaa7e1f26064"}
            ),
        ),
        # huntdark.z5
        "dba237b3f5c37c5cf26cf2575b483cb61c00b2b5d4d76654216ca0b17f9546a6": StoryProfile(
            max_score=1,
            player_object=17,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_signed=False,
            victory_score=1,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129",
                    "d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6",
                }
            ),
            victory_hashes=frozenset(
                {"a3003457f50a4ca970976b0bd47ac5ca95ab14c03377931eb80dff6e1125b8b2"}
            ),
        ),
        # inhumane.z5
        "c8c468e9de912d53c468e6620f133fef827f8078f8f8beae7084e532cbd29e19": StoryProfile(
            max_score=90,
            player_object=15,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_global=3,
            score_byte=True,
            score_signed=False,
            moves_global=4,
            victory_overrides_loss=True,
            victory_hashes=frozenset(
                {"085e8510c47345f9014070ad233168e7c4ac2110ce66ca9f5feb52e7a1dc550f"}
            ),
        ),
        # jewel.z5
        "aa2a87e5d0155b430c39e894a2b9e2e7a6ab7b1fec42f163aa7e1f30fc4cfcc5": StoryProfile(
            max_score=90,
            player_object=211,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_byte=True,
            score_signed=False,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129",
                    "d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # karn.z5
        "cd38f9b31949dbc3ce723e5f650dc06238dd9f3776974365d4a92f473155cad4": StoryProfile(
            max_score=170,
            player_object=20,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_byte=True,
            score_signed=False,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129",
                    "d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # library.z5
        "df82748cb949801c336b7765310165a4e292a191685bdba54b67f2b29f6d23ff": StoryProfile(
            max_score=30,
            player_object=15,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_global=9,
            score_byte=True,
            score_signed=False,
            moves_global=10,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "0593f62254ab1ba4c08ae1d643013e6e4942512531c1ac45185113460cdc5975",
                    "07ed99552cab0fb52e015f9eb90f75a2c2f2ee9accbafe6d1cfc55e21189a0d3",
                    "14fa2be9ac4fb1e2f5a63a5929070a9a3235a0900ff94066c68e0c004ca0dc5c",
                    "21e736aeb331b6c5c3d0e42e7f7fa73f071f40328b31f9fac5a698ad04294b56",
                    "53e4c00dae50eb9bc7043b906c78a1b9d7f21315005b1c84d689fcf26fbd3c78",
                    "664ffec35974b351d7be2ca1f03decebddf6bd9581982e28af917d1febcaf72d",
                    "839f7a8bff3327cad69b34ca5998f3481be181d9a5570c44fc45dbed649d2452",
                    "83ce00cf2113664b043e2aad373e072043739a9b92ed4f1c1a4c58380dd40ca7",
                    "8c3b6de036e9a295f30bd3a5df9c5ef42fa1bb0c27f09649ba0197d783a7ffdb",
                    "a1b0995061d63aced61496e5445e44c857c3b858ac30715c5ce7639b7bca0ba9",
                    "a321e0ea7e83432189ae2d11e24b88173b1599ff37aec3b0442a42aaed1949a6",
                    "be65d4eba3a771f50a7822f0ef5e4d7003b24a72b76c290c493a681112cfb54b",
                    "cc8df4cb69cf0b2495cfb7b19d8056c5014e685dbdbff5006a39822bf1300db6",
                    "d12e13d22f49290f2e644fce07dfe2cbcda85480a07681258255a5811b97fcf8",
                    "d86b01f7c946960377f3232030e50ee65494287d430a039422120c30a6161991",
                    "e6bf6cc05cb133cdb3e64d42db11f463ca852c728c9fd75e266fcb42be867d03",
                    "f6c0646c40fb2fc51984a2ef85eb22134972f8c8d2e778a834b5114410f26a2c",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # loose.z5
        "8d286732a28cec39cc93005187fc469b68fcfbf5b84d4806a99dd6ca482cb08f": StoryProfile(
            max_score=50,
            player_object=34,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_byte=True,
            score_signed=False,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "0593f62254ab1ba4c08ae1d643013e6e4942512531c1ac45185113460cdc5975",
                    "07ed99552cab0fb52e015f9eb90f75a2c2f2ee9accbafe6d1cfc55e21189a0d3",
                    "14fa2be9ac4fb1e2f5a63a5929070a9a3235a0900ff94066c68e0c004ca0dc5c",
                    "21e736aeb331b6c5c3d0e42e7f7fa73f071f40328b31f9fac5a698ad04294b56",
                    "53e4c00dae50eb9bc7043b906c78a1b9d7f21315005b1c84d689fcf26fbd3c78",
                    "664ffec35974b351d7be2ca1f03decebddf6bd9581982e28af917d1febcaf72d",
                    "839f7a8bff3327cad69b34ca5998f3481be181d9a5570c44fc45dbed649d2452",
                    "83ce00cf2113664b043e2aad373e072043739a9b92ed4f1c1a4c58380dd40ca7",
                    "8c3b6de036e9a295f30bd3a5df9c5ef42fa1bb0c27f09649ba0197d783a7ffdb",
                    "a1b0995061d63aced61496e5445e44c857c3b858ac30715c5ce7639b7bca0ba9",
                    "a321e0ea7e83432189ae2d11e24b88173b1599ff37aec3b0442a42aaed1949a6",
                    "be65d4eba3a771f50a7822f0ef5e4d7003b24a72b76c290c493a681112cfb54b",
                    "cc8df4cb69cf0b2495cfb7b19d8056c5014e685dbdbff5006a39822bf1300db6",
                    "d12e13d22f49290f2e644fce07dfe2cbcda85480a07681258255a5811b97fcf8",
                    "d86b01f7c946960377f3232030e50ee65494287d430a039422120c30a6161991",
                    "e6bf6cc05cb133cdb3e64d42db11f463ca852c728c9fd75e266fcb42be867d03",
                    "f6c0646c40fb2fc51984a2ef85eb22134972f8c8d2e778a834b5114410f26a2c",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # ludicorp.z5
        "d1745be6beba0e74830d9ed0af9928aea10c5a2a345e5a68ff06db7d40f041c3": StoryProfile(
            max_score=150,
            player_object=20,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_global=13,
            score_byte=True,
            score_signed=False,
            moves_global=8,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129",
                    "d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # moonlit.z5
        "ee83554ca711f53a5a4c7d1d31b3c265a95b592cab8098175477245ec0a4085e": StoryProfile(
            max_score=1,
            player_object=20,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_signed=False,
            victory_score=1,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129",
                    "d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # murdac.z5
        "bc6e77c7aaa701ddc359493a154995dfaeaf7b191beaba0566e87327728ea5ef": StoryProfile(
            max_score=250,
            player_object=7,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_global=10,
            score_byte=True,
            score_signed=False,
            moves_global=18,
            victory_overrides_loss=True,
            victory_hashes=frozenset(
                {"3b97419d7dd2f4a47f74947edab9012fc6fbde62cd20aa3b06c95de4ab21c7a0"}
            ),
        ),
        # night.z5
        "095a32cbe37c93cebf9e6a20abcf1fcc1252d97f3b67353a0c5390375eabc887": StoryProfile(
            max_score=10,
            player_object=15,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_global=3,
            score_byte=True,
            score_signed=False,
            moves_global=4,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129",
                    "d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6",
                }
            ),
            victory_hashes=frozenset(
                {"5849fc77e56b68427a3ecd1f0aa9e6f85396ddd499c7b54c3746a4c25d789650"}
            ),
        ),
        # omniquest.z5
        "b80f52c22e4ebfe0c1c65517aa3296d0432172ce7dd55f8b957159c7f7bffaa3": StoryProfile(
            max_score=50,
            player_object=20,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_global=2,
            score_byte=True,
            score_signed=False,
            moves_global=3,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129",
                    "d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # pentari.z5
        "19cf3c8b2a6e4eb7c82391db7bafc8a6dd07ba4874897e741de100e1df9d875c": StoryProfile(
            max_score=70,
            player_object=20,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_byte=True,
            score_signed=False,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129",
                    "d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # reverb.z5
        "b5e50b3f46f963163515e65d80589cb59586234c58792851f64aabae38405b77": StoryProfile(
            max_score=50,
            player_object=20,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_global=7,
            score_byte=True,
            score_signed=False,
            moves_global=8,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "21e736aeb331b6c5c3d0e42e7f7fa73f071f40328b31f9fac5a698ad04294b56",
                    "f6c0646c40fb2fc51984a2ef85eb22134972f8c8d2e778a834b5114410f26a2c",
                }
            ),
            victory_hashes=frozenset(
                {"697d7aff47acd3afeeba247bf39f2a2cbba4cc8041946ec07ac26761b1cfc599"}
            ),
        ),
        # spirit.z5
        "d575ba4e1c7e9e50eb7c45550ccb5f155287f2346274d26d7d84eb434278e0b7": StoryProfile(
            max_score=250,
            player_object=15,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_global=8,
            score_byte=True,
            score_signed=False,
            moves_global=9,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129",
                    "d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # temple.z5
        "dffea77ceabddfba1354a405ae5d3cf2f244ee937806cdbaf84cdcba00959f1e": StoryProfile(
            max_score=35,
            player_object=89,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_byte=True,
            score_signed=False,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129",
                    "d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # theatre.z5
        "08852cc883a96edeb1d113265c13076fdf98a1ffab2a412268bf8714a3a5564d": StoryProfile(
            max_score=50,
            player_object=15,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129",
                    "d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # tryst205.z5
        "6834e1717ddd1fc6ab86c4f5ff9fac513da5a187804c7159c4ffcc596e766f2a": StoryProfile(
            max_score=350,
            player_object=20,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "d0d315b93630d583d3517bd77046c817a1bbbc2ba4b885258b161be053f9f129",
                    "d6815c21cb6d68ec2a4ecac55eeee65d05063b1fc21daf30846806c25270fcd6",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # weapon.z5
        "e78dd4c6dea28215c6ef2260e64f9dfae154a4640140e5b99e9098a5860f667a": StoryProfile(
            max_score=1,
            player_object=20,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_signed=False,
            victory_score=1,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {"c965fe2e1c9854fb6252938c67bc90f15e789cd811ef71c532bfb94748551a96"}
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # zenon.z5
        "e05833b393ac9979d78039ff34430c772a1cb735e03e5e751e2c635dfd6037cc": StoryProfile(
            max_score=20,
            player_object=20,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_global=2,
            moves_global=3,
            victory_overrides_loss=True,
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
        # ztuu.z5
        "cb93836749bcf3fdc5d816538db217f8612f6df1147ff0eb5fc3aabd60bcf1d8": StoryProfile(
            max_score=100,
            player_object=20,
            loss_lines=frozenset(),
            victory_lines=frozenset(),
            score_byte=True,
            score_signed=False,
            moves_byte=True,
            victory_overrides_loss=True,
            loss_hashes=frozenset(
                {
                    "0593f62254ab1ba4c08ae1d643013e6e4942512531c1ac45185113460cdc5975",
                    "07ed99552cab0fb52e015f9eb90f75a2c2f2ee9accbafe6d1cfc55e21189a0d3",
                    "14fa2be9ac4fb1e2f5a63a5929070a9a3235a0900ff94066c68e0c004ca0dc5c",
                    "21e736aeb331b6c5c3d0e42e7f7fa73f071f40328b31f9fac5a698ad04294b56",
                    "53e4c00dae50eb9bc7043b906c78a1b9d7f21315005b1c84d689fcf26fbd3c78",
                    "664ffec35974b351d7be2ca1f03decebddf6bd9581982e28af917d1febcaf72d",
                    "839f7a8bff3327cad69b34ca5998f3481be181d9a5570c44fc45dbed649d2452",
                    "83ce00cf2113664b043e2aad373e072043739a9b92ed4f1c1a4c58380dd40ca7",
                    "8c3b6de036e9a295f30bd3a5df9c5ef42fa1bb0c27f09649ba0197d783a7ffdb",
                    "a1b0995061d63aced61496e5445e44c857c3b858ac30715c5ce7639b7bca0ba9",
                    "a321e0ea7e83432189ae2d11e24b88173b1599ff37aec3b0442a42aaed1949a6",
                    "be65d4eba3a771f50a7822f0ef5e4d7003b24a72b76c290c493a681112cfb54b",
                    "cc8df4cb69cf0b2495cfb7b19d8056c5014e685dbdbff5006a39822bf1300db6",
                    "d12e13d22f49290f2e644fce07dfe2cbcda85480a07681258255a5811b97fcf8",
                    "d86b01f7c946960377f3232030e50ee65494287d430a039422120c30a6161991",
                    "e6bf6cc05cb133cdb3e64d42db11f463ca852c728c9fd75e266fcb42be867d03",
                    "f6c0646c40fb2fc51984a2ef85eb22134972f8c8d2e778a834b5114410f26a2c",
                }
            ),
            victory_hashes=frozenset(
                {"a9cb91961da0ab9c2b4c970664745fed4e213cb29ae78a2f4098037401e18d5b"}
            ),
        ),
    }
)
