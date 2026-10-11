"""Record reference behavior through documented public APIs, never source."""

from fernz import Story

from .state_bridge import StateBridge
from .v3_cases import GAMES, HALTED_VICTORIES
from .v3_oracle import assert_public_object, object_count, object_records
from .v3_vectors import reference_text
from .vector_archive import digest, state_fingerprint


class Reference:
    def __init__(self, path, game, seed=None):
        from jericho import FrotzEnv

        self.game = game
        self.seed = GAMES[game]["seed"] if seed is None else seed
        self.story = Story.from_file(path)
        assert digest(path.read_bytes()) == GAMES[game]["file_sha256"]
        self.env = FrotzEnv(str(path), seed=self.seed)
        assert self.env.seed(self.seed) == self.seed
        self.initial = self.env.reset()
        # Advertise the same text-only screen capabilities through the public
        # snapshot. For example, Seastalker otherwise adds screen-specific
        # sonarscope advice. No private/native interpreter interfaces are used.
        self.text_capabilities()
        self.bridge = StateBridge(self.story, self.env.get_state(), seed=self.seed)

    def text_capabilities(self):
        native = self.env.get_state()
        flags = (int(native[0][1]) & ~0x70) | 0x10
        if flags != int(native[0][1]):
            ram = native[0].copy()
            ram[1] = flags
            self.env.set_state((ram, *native[1:]))

    def close(self):
        self.env.close()

    def capture(self, action, response):
        observation, reward, done, info = response
        native = self.env.get_state()
        halted = self.game in HALTED_VICTORIES and bool(self.env.victory())
        world = self.env.get_world_objects(clean=False)
        assert len(world) == GAMES[self.game]["world_count"]
        data = native[0].tobytes() + self.story.data[len(native[0]) : self.story.size]
        canonical = object_records(data, object_count(self.story.data))
        for obj, record in zip(world, canonical[: len(world)], strict=True):
            assert_public_object(obj, record)
        player = self.env.get_player_object()
        location = self.env.get_player_location()
        inventory = self.env.get_inventory()
        assert int(player.num) == GAMES[self.game]["player"]
        for obj in (player, location, *inventory):
            if obj is not None:
                assert_public_object(obj, canonical[int(obj.num)])
        parent = canonical[int(player.num)]["parent"]
        if location is None:
            # Direct public lookup also hides unnamed locations, such as
            # Seastalker's initial naming prompt after an in-game restart.
            assert parent == 0 or canonical[parent]["name"] == ""
        else:
            assert int(location.num) == parent
        carried = []
        number = canonical[int(player.num)]["child"]
        while number:
            assert number not in {obj["num"] for obj in carried}
            carried.append(canonical[number])
            number = canonical[number]["sibling"]
        native_numbers = [int(obj.num) for obj in inventory]
        assert native_numbers == [obj["num"] for obj in carried[: len(inventory)]]
        if len(inventory) != len(carried):
            # The public reference stops its sibling walk at an unnamed node.
            assert carried[len(inventory)]["name"] == ""
            assert self.env.get_object(carried[len(inventory)]["num"]) is None
        queries = {
            "world_count": len(canonical),
            "world_sha256": digest(canonical),
            "inventory_sha256": digest(carried),
            "player_sha256": digest(canonical[int(player.num)]),
            "location_sha256": digest(canonical[parent]) if parent else digest(None),
            "location": parent,
            "player": int(player.num),
            "score": int(self.env.get_score()),
            "moves": int(self.env.get_moves()),
            "max_score": int(self.env.get_max_score()),
            "game_over": bool(self.env.game_over()),
            "victory": bool(self.env.victory()),
        }
        assert queries["max_score"] == GAMES[self.game]["max_score"]
        return {
            "action": action,
            "observation_sha256": digest(
                reference_text(observation, (obj["name"] for obj in canonical)).encode()
            ),
            "reward": int(reward),
            "done": bool(done),
            "halted": halted,
            "info": {key: int(info[key]) for key in ("score", "moves")},
            "queries": queries,
            "state": None if halted else state_fingerprint(self.bridge.from_jericho(native)),
        }

    def opening(self):
        observation, info = self.initial
        return self.capture(None, (observation, 0, False, info))

    def step(self, action):
        response = self.env.step(action)
        # A story restart resets host capability bits as well as game memory.
        self.text_capabilities()
        return self.capture(action, response)
