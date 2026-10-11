"""Portable ZIP expectations and Zork fingerprints; no reference dependency on replay."""

import json
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .zork_compat import NAME_DIFFERENCES, UNNAMED_OBJECTS

ARCHIVE_PATH = Path(__file__).parent / "vectors" / "zork1_vectors.zip"
STORYFILES_PATH = Path(__file__).parent / "vectors" / "storyfiles.zip"
FORMAT_VERSION = 1
REFERENCE_VERSION = "3.3.1"


def json_bytes(value):
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode()


def digest(value):
    return sha256(value if isinstance(value, bytes) else json_bytes(value)).hexdigest()


def state_fingerprint(state):
    """Fingerprint VM fields measurable through the public reference snapshot.

    Display state is not exposed by the reference. Fernz's complete display
    checkpoint is checked separately by replay/copy and protocol tests.
    """
    result = asdict(state)
    result.pop("output", None)
    result["format_version"] = 2
    result["ram_sha256"] = digest(result.pop("ram"))
    result["frames_sha256"] = digest(result.pop("frames"))
    return result


def object_record(obj, *, fernz=False):
    result = {
        "num": int(obj.num),
        "name": obj.name,
        "parent": int(obj.parent),
        "sibling": int(obj.sibling),
        "child": int(obj.child),
        "attr": [int(value) for value in obj.attr],
        "properties": [int(value) for value in obj.properties],
    }
    if fernz and obj.num in NAME_DIFFERENCES:
        full, reference = NAME_DIFFERENCES[obj.num]
        assert obj.name == full, (obj.num, obj.name)
        result["name"] = reference
    if fernz and obj.num in UNNAMED_OBJECTS:
        # These real nodes are absent from the public reference object list.
        # Their data is still covered by the complete dynamic-memory hash.
        assert obj.name == ""
        result = {
            "num": 0,
            "name": "",
            "parent": 0,
            "sibling": 0,
            "child": 0,
            "attr": [0] * 32,
            "properties": [0] * 16,
        }
    return result


def query_fingerprint(env, *, fernz=False):
    world = env.get_world_objects(clean=False)
    return {
        "world_count": len(world),
        "world_sha256": digest([object_record(obj, fernz=fernz) for obj in world]),
        "inventory_sha256": digest(
            [object_record(obj, fernz=fernz) for obj in env.get_inventory()]
        ),
        "player_sha256": digest(object_record(env.get_player_object(), fernz=fernz)),
        "location_sha256": digest(object_record(env.get_player_location(), fernz=fernz)),
        "location": int(env.get_player_location().num),
        "score": int(env.get_score()),
        "moves": int(env.get_moves()),
        "max_score": int(env.get_max_score()),
        "game_over": bool(env.game_over()),
        "victory": bool(env.victory()),
    }


def observation_text(observation, mode):
    """Apply only the explicitly measured presentation differences."""
    from .observation_helpers import plain_text

    observation = plain_text(observation).replace("\r\n", "\n")
    if mode == "opening":
        title = "ZORK I: The Great Underground Empire\n"
        assert observation.startswith(title) and observation.endswith("\n")
        return observation.removeprefix(title)
    assert observation.startswith("\n")
    if mode == "turn":
        assert observation.endswith("\n")
        return observation[1:]
    if mode == "restart-confirmation":
        assert not observation.endswith(" >")
        return observation[1:]
    if mode == "ending":
        assert observation.endswith("\n")
        return observation[1:] + "\n"
    raise ValueError(f"Unknown observation mode: {mode}")


def write_archive(path, documents):
    """Write deterministic members; callers arrange atomic replacement."""
    with ZipFile(path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name, document in sorted(documents.items()):
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(
                entry, json_bytes(document), compress_type=ZIP_DEFLATED, compresslevel=9
            )


def read_archive(path=ARCHIVE_PATH):
    """Read and verify ZIP members in memory, never extracting them to disk."""
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or "manifest.json" not in names:
            raise ValueError("Vector ZIP has duplicate members or no manifest")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest["format_version"] != FORMAT_VERSION:
            raise ValueError("Unsupported vector format version")
        if set(names) != {"manifest.json", *manifest["files"]}:
            raise ValueError("Vector ZIP members do not match its manifest")
        documents = {"manifest.json": manifest}
        for name, metadata in manifest["files"].items():
            payload = archive.read(name)
            if sha256(payload).hexdigest() != metadata["sha256"]:
                raise ValueError(f"Vector member checksum mismatch: {name}")
            document = json.loads(payload)
            # Trace members carry case/record counts. Story metadata members
            # contain one document each and need only the content checksum.
            if ("cases" in metadata or "records" in metadata) and (
                len(document["cases"]) != metadata["cases"]
                or sum(len(case["steps"]) for case in document["cases"]) != metadata["records"]
            ):
                raise ValueError(f"Vector member counts do not match: {name}")
            documents[name] = document
    return documents
