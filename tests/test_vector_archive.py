"""The portable archive must fail closed on missing, corrupt, or stale metadata."""

import json
import re
from pathlib import Path
from zipfile import ZipFile

import pytest

from .vector_archive import digest, json_bytes, read_archive, write_archive


def example():
    document = {"cases": [{"id": "probe", "steps": [{"action": "look"}]}]}
    return {
        "probe.json": document,
        "manifest.json": {
            "format_version": 1,
            "files": {
                "probe.json": {"sha256": digest(json_bytes(document)), "cases": 1, "records": 1}
            },
        },
    }


def test_zip_is_repeatable_and_read_in_memory(tmp_path):
    documents = example()
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    write_archive(first, documents)
    write_archive(second, dict(reversed(list(documents.items()))))
    assert first.read_bytes() == second.read_bytes()
    assert read_archive(first) == documents
    assert sorted(path.name for path in tmp_path.iterdir()) == ["first.zip", "second.zip"]
    with ZipFile(first) as archive:
        assert all(entry.date_time == (1980, 1, 1, 0, 0, 0) for entry in archive.infolist())
        assert json.loads(archive.read("probe.json")) == documents["probe.json"]


@pytest.mark.parametrize(
    "damage,match",
    [
        ("missing-manifest", "no manifest"),
        ("missing-case", "members"),
        ("extra-case", "members"),
        ("format", "format"),
        ("checksum", "checksum"),
        ("counts", "counts"),
        ("duplicate", "duplicate"),
    ],
)
def test_incomplete_or_modified_zip_fails(tmp_path, damage, match):
    documents = example()
    manifest = documents["manifest.json"]
    if damage == "missing-manifest":
        del documents["manifest.json"]
    elif damage == "missing-case":
        del documents["probe.json"]
    elif damage == "extra-case":
        documents["unexpected.json"] = {}
    elif damage == "format":
        manifest["format_version"] = 99
    elif damage == "checksum":
        documents["probe.json"]["cases"][0]["steps"][0]["action"] = "wait"
    elif damage == "counts":
        manifest["files"]["probe.json"]["records"] += 1
    path = tmp_path / "vectors.zip"
    write_archive(path, documents)
    if damage == "duplicate":
        with ZipFile(path, "a") as archive, pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("probe.json", json_bytes(documents["probe.json"]))
    with pytest.raises(ValueError, match=match):
        read_archive(path)


def test_v5_breadth_records_store_hashes_not_game_content():
    from .v5_corpus import COMMANDS, GAMES

    for game in GAMES:
        documents = read_archive(Path(__file__).parent / "vectors" / f"{game}_vectors.zip")
        cases = documents["breadth.json"]["cases"]
        assert len(cases) == 2
        assert tuple(record["action"] for record in cases[0]["steps"][1:]) == COMMANDS
        for case in cases:
            assert len(case["steps"]) == 6
            for record in case["steps"]:
                assert set(record) == {
                    "action",
                    "observation_sha256",
                    "objects",
                    "input_address",
                    "character_input",
                    "rng",
                }
                assert set(record["objects"]) == {"count", "entries_sha256", "tables_sha256"}
                hashes = [record["objects"][key] for key in ("entries_sha256", "tables_sha256")]
                if record["observation_sha256"] is not None:
                    hashes.append(record["observation_sha256"])
                assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes)
                assert all(type(value) is int for value in record["rng"])
                assert type(record["input_address"]) is int
                assert type(record["character_input"]) is bool


def test_full_v5_records_do_not_embed_narrative_or_state_payloads():
    from .v5_trajectory_cases import GAMES

    fields = {
        "action",
        "queries",
        "reward",
        "reference_done",
        "info",
        "terminal_menu",
        "input_address",
        "character_input",
        "rng",
        "objects",
        "upper_window_sha256",
        "observation_sha256",
    }
    for game in GAMES:
        documents = read_archive(Path(__file__).parent / "vectors" / f"{game}_vectors.zip")
        for name, document in documents.items():
            if name in ("manifest.json", "breadth.json"):
                continue
            for case in document["cases"]:
                for record in case["steps"]:
                    assert set(record) == fields
                    for value in (record["observation_sha256"], record["upper_window_sha256"]):
                        assert value is None or re.fullmatch(r"[0-9a-f]{64}", value)
                    for key, value in record["queries"].items():
                        if isinstance(value, str):
                            assert key.endswith("_sha256") and re.fullmatch(r"[0-9a-f]{64}", value)
                        else:
                            assert type(value) in (int, bool, list)


def test_remaining_v5_walkthroughs_store_only_commands_metadata_and_hashes():
    from .v5_walkthrough_cases import GAMES

    fields = {
        "action",
        "queries",
        "reference_outcomes",
        "reward",
        "reference_done",
        "info",
        "reference_info",
        "halted",
        "input_address",
        "character_input",
        "rng",
        "objects",
        "globals_sha256",
        "text_group_end",
        "text_sha256",
    }

    def metadata(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(child, str):
                    assert key.endswith("_sha256") and re.fullmatch(r"[0-9a-f]{64}", child)
                else:
                    metadata(child)
        elif isinstance(value, list):
            assert all(type(child) is int for child in value)
        else:
            assert value is None or type(value) in (int, bool)

    for game, case in GAMES.items():
        documents = read_archive(Path(__file__).parent / "vectors" / f"{game}_vectors.zip")
        assert set(documents) == {
            "manifest.json",
            "breadth.json",
            "walkthrough.json",
            "counters.json",
        }
        route = documents["walkthrough.json"]["cases"][0]
        assert len(route["steps"]) == case["length"] + 1
        assert route["steps"][0]["action"] is None
        for record in route["steps"]:
            assert set(record) == fields
            assert record["action"] is None or isinstance(record["action"], str)
            metadata({key: value for key, value in record.items() if key != "action"})
        for record in documents["counters.json"]["cases"][0]["steps"]:
            assert set(record) == {"field", "value", "score", "moves"}
            assert record["field"] in ("score", "moves")
            assert all(type(record[key]) is int for key in ("value", "score", "moves"))
