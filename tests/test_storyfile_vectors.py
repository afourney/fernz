"""Check the independent recorder using hand-assembled images, without ROMs."""

from hashlib import sha256

import pytest

from .scripts import generate_zork1_vectors
from .scripts.storyfile_vectors import record_story
from .story_corpus import GAMES
from .story_files import put_word, story_bytes
from .vector_archive import read_archive


def test_generator_rejects_colliding_archive_paths(tmp_path):
    output = str(tmp_path / "both.zip")
    with pytest.raises(SystemExit) as exc:
        generate_zork1_vectors.main(["--output", output, "--storyfiles-output", output])
    assert exc.value.code == 2
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("version", (3, 4, 5, 8))
def test_metadata_recorder_obeys_version_units_extensions_and_padding(version):
    data = bytearray(story_bytes(version))
    put_word(data, 0x100, 0x1234)
    # Optional V5+ fields must be ignored for older formats, even if nonzero.
    put_word(data, 0x34, 0x350)
    put_word(data, 0x36, 0x2E0)
    if version >= 5:
        put_word(data, 0x2E0, 1)
        put_word(data, 0x2E2, 0x5678)
    checksum = 277 if version >= 5 else 70
    put_word(data, 0x1C, checksum)
    padded = bytes(data) + b"\xff" * 128
    record = record_story(padded)
    assert record["header"]["version"] == version
    assert record["header"]["release"] == 42
    assert record["header"]["serial"] == "260101"
    assert record["header"]["file_length"] == record["story_size"] == 4096
    assert record["file_size"] == 4224
    assert record["file_sha256"] == sha256(padded).hexdigest()
    assert record["memory_sha256"] == sha256(data).hexdigest()
    assert record["packed_address_scale"] == {3: 2, 4: 4, 5: 4, 8: 8}[version]
    assert record["entry_address"] == 0x401
    assert record["first_global"] == 0x1234
    assert record["calculated_checksum"] == record["header"]["checksum"] == checksum
    assert record["extension_words"] == ([1, 0x5678] if version >= 5 else [])
    assert record["header"]["alphabet_table"] == (0x350 if version >= 5 else None)
    assert record["header"]["extension_table"] == (0x2E0 if version >= 5 else None)
    with pytest.raises(ValueError, match="length"):
        record_story(bytes(data[:-1]))
    data[-1] = 1
    with pytest.raises(ValueError, match="checksum"):
        record_story(bytes(data))


def test_story_only_command_needs_no_reference_and_detects_changed_inputs(tmp_path, monkeypatch):
    def unexpected_reference(*args, **kwargs):
        pytest.fail("Story metadata generation must not use the reference interpreter")

    monkeypatch.setattr(generate_zork1_vectors, "version", unexpected_reference)
    monkeypatch.setattr(generate_zork1_vectors, "generate", unexpected_reference)
    suite = tmp_path / "suite"
    suite.mkdir()
    for version, filenames in GAMES.items():
        for filename in filenames:
            (suite / filename).write_bytes(story_bytes(version))
    output = tmp_path / "storyfiles.zip"
    args = ["--only", "storyfiles", "--suite", str(suite), "--storyfiles-output", str(output)]
    generate_zork1_vectors.main(args)
    documents = read_archive(output)
    assert len(documents) == 57
    assert documents["manifest.json"]["story_count"] == 56
    before = output.read_bytes(), output.stat().st_mtime_ns
    generate_zork1_vectors.main([*args, "--check"])
    assert (output.read_bytes(), output.stat().st_mtime_ns) == before
    changed = bytearray((suite / "zork1.z5").read_bytes())
    put_word(changed, 2, 99)  # Release is outside the checksum's covered bytes.
    (suite / "zork1.z5").write_bytes(changed)
    with pytest.raises(SystemExit) as exc:
        generate_zork1_vectors.main([*args, "--check"])
    assert exc.value.code == 1
    assert (output.read_bytes(), output.stat().st_mtime_ns) == before
    (suite / "zork1.z5").unlink()
    with pytest.raises(FileNotFoundError):
        generate_zork1_vectors.main(args)
    assert (output.read_bytes(), output.stat().st_mtime_ns) == before
