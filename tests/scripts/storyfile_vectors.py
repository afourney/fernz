"""Decode retained-ROM metadata directly from Standard 1.1, without Fernz APIs.

This recorder covers the corpus's V3, V4, V5, and V8 files. Header fields and
length units follow §11 and Appendix B; checksum bytes follow §15's verify.
It is not a general story validator or an interpreter.
"""

from struct import unpack_from

from ..game_files import GAMES_ARCHIVE_URL
from ..story_corpus import GAMES
from ..vector_archive import FORMAT_VERSION, digest, json_bytes

SPEC_URL = "https://inform-fiction.org/zmachine/standards/z1point1/sect11.html"
WORD_FIELDS = {
    "release": 0x02,
    "high_memory": 0x04,
    "initial_value": 0x06,
    "dictionary": 0x08,
    "object_table": 0x0A,
    "globals_table": 0x0C,
    "static_memory": 0x0E,
    "flags2": 0x10,
    "abbreviations_table": 0x18,
    "checksum": 0x1C,
}


def record_story(data):
    def word(offset):
        return unpack_from(">H", data, offset)[0]

    version = data[0]
    scale = {3: 2, 4: 4, 5: 4, 8: 8}[version]
    size = word(0x1A) * scale
    if not 64 <= size <= len(data):
        raise ValueError("Retained stories must declare a complete image length")
    calculated_checksum = sum(data[64:size]) % 65536
    if calculated_checksum != word(0x1C):
        raise ValueError("Retained story checksum mismatch")
    header = {name: word(offset) for name, offset in WORD_FIELDS.items()}
    header.update(
        version=version,
        serial=data[0x12:0x18].decode("ascii"),
        flags1=data[1],
        file_length=size,
        # The retained versions start at a byte-addressed PC and have none of
        # the routine/string offsets defined for V6/V7.
        routine_offset=0,
        string_offset=0,
        alphabet_table=word(0x34) if version >= 5 else None,
        extension_table=word(0x36) if version >= 5 else None,
    )
    extension = header["extension_table"]
    extension_words = (
        list(unpack_from(f">{word(extension) + 1}H", data, extension)) if extension else []
    )
    dynamic_end = header["static_memory"]
    globals_start = header["globals_table"]
    return {
        "file_size": len(data),
        "file_sha256": digest(data),
        "story_size": size,
        "header": header,
        "entry_address": header["initial_value"],
        "entry_is_routine": False,
        "packed_address_scale": scale,
        "extension_words": extension_words,
        "calculated_checksum": calculated_checksum,
        "checksum_valid": True,
        "memory_sha256": digest(data[:size]),
        "dynamic_sha256": digest(data[:dynamic_end]),
        "static_sha256": digest(data[dynamic_end:size]),
        "globals_sha256": digest(data[globals_start : globals_start + 480]),
        "first_global": word(globals_start),
    }


def generate_storyfiles(suite):
    documents = {}
    for version, filenames in GAMES.items():
        for filename in filenames:
            record = record_story((suite / filename).read_bytes())
            if record["header"]["version"] != version:
                raise ValueError(f"Unexpected version for retained story: {filename}")
            documents[filename + ".json"] = record
    documents["manifest.json"] = {
        "format_version": FORMAT_VERSION,
        "kind": "storyfiles",
        "source": GAMES_ARCHIVE_URL,
        "oracle": {"method": "specification and original file bytes", "specification": SPEC_URL},
        "story_count": sum(len(names) for names in GAMES.values()),
        "files": {
            name: {"sha256": digest(json_bytes(record))}
            for name, record in sorted(documents.items())
        },
    }
    return documents
