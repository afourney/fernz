"""The portable archive must fail closed on missing, corrupt, or stale metadata."""

import json
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
