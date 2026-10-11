"""V5 query fingerprints from documented APIs and the specified RAM layout."""

from .vector_archive import digest


def object_record(obj):
    return {
        "num": int(obj.num),
        "name": obj.name,
        "parent": int(obj.parent),
        "sibling": int(obj.sibling),
        "child": int(obj.child),
        # The measured public reference exposes 32 flags even for V5. Fernz
        # retains all 48; check the remaining flags independently from RAM.
        "attr": [int(value) for value in obj.attr[:32]],
        "properties": [int(value) for value in obj.properties],
    }


def query_fingerprint(env, *, fernz=False):
    world = env.get_world_objects(clean=False)
    player = env.get_player_object()
    location = env.get_player_location()
    inventory = env.get_inventory()
    snapshot = env.get_state()
    if fernz:
        attributes = [obj.attr for obj in world[1:]]
        rng = snapshot.rng
        random = (rng.state, rng.period, rng.position)
        assert all(len(obj.attr) == 48 for obj in world)
    else:
        ram = snapshot[0].tobytes()
        base = int.from_bytes(ram[10:12], "big") + 126
        attributes = [
            [(ram[base + 14 * n + bit // 8] >> (7 - bit % 8)) & 1 for bit in range(48)]
            for n in range(len(world) - 1)
        ]
        a, period, counter = snapshot[7]
        random = (int(a) & 0x7FFFFFFF, int(period), int(counter) if period else 0)
    assert env.get_object(0) is None
    assert env.get_object(len(world)) is None
    for obj in world[1:]:
        assert object_record(env.get_object(int(obj.num))) == object_record(obj)
    return {
        "world_count": len(world),
        "world_sha256": digest([object_record(obj) for obj in world]),
        "attributes_sha256": digest(attributes),
        "player_sha256": digest(object_record(player)),
        "location_sha256": digest(object_record(location)) if location else None,
        "inventory_sha256": digest([object_record(obj) for obj in inventory]),
        "player": int(player.num),
        "location": int(location.num) if location else 0,
        "inventory": [int(obj.num) for obj in inventory],
        "score": int(env.get_score()),
        "moves": int(env.get_moves()),
        "max_score": int(env.get_max_score()),
        "game_over": bool(env.game_over()),
        "victory": bool(env.victory()),
        "rng": list(random),
    }
