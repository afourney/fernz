"""Immutable story images, using Standard 1.1 sections 1 and 11 and Appendix B."""

from dataclasses import dataclass, field
from operator import index
from os import PathLike
from pathlib import Path
from stat import S_ISREG

# Versions this package can execute; all V1-V8 stories can be loaded and inspected.
EXECUTABLE_VERSIONS = (3, 4, 5, 8)


class StoryFormatError(ValueError):
    """A file is not a structurally valid, raw V1-V8 Z-machine story."""


def _word(data: bytes, address: int) -> int:
    return (data[address] << 8) | data[address + 1]


def _packed_value(value: int) -> int:
    value = index(value)
    if not 0 <= value <= 0xFFFF:
        raise ValueError("A packed address must be an unsigned 16-bit integer")
    return value


@dataclass(frozen=True, slots=True)
class StoryHeader:
    """Initial header values; addresses and offsets are expressed in bytes.

    Fields unavailable in the story's version are None. A zero optional table
    address means the table is absent. Serial codes are conventional ASCII;
    undecodable characters are replaced, with original bytes retained in Story.
    """

    version: int
    release: int
    serial: str | None
    flags1: int
    flags2: int
    high_memory: int
    static_memory: int
    initial_value: int
    dictionary: int
    object_table: int
    globals_table: int
    abbreviations_table: int | None
    file_length: int | None
    checksum: int | None
    routine_offset: int
    string_offset: int
    alphabet_table: int | None
    extension_table: int | None
    _extension: tuple[int, ...] = field(repr=False)

    @property
    def entry_is_routine(self) -> bool:
        """Whether startup calls a main routine instead of setting the PC."""
        return self.version == 6

    @property
    def entry_address(self) -> int:
        """Return the initial PC, or the main routine's header address in V6."""
        if self.entry_is_routine:
            return self.unpack_routine_address(self.initial_value)
        return self.initial_value

    @property
    def packed_address_scale(self) -> int:
        """Return the multiplier used for packed routine and string addresses."""
        return 2 if self.version <= 3 else 8 if self.version == 8 else 4

    def unpack_routine_address(self, packed: int) -> int:
        """Decode an address without dereferencing it or applying call semantics.

        In particular, handling a call to packed address zero belongs to the CPU.
        """
        return self.packed_address_scale * _packed_value(packed) + self.routine_offset

    def unpack_string_address(self, packed: int) -> int:
        """Decode a packed string address without dereferencing it."""
        return self.packed_address_scale * _packed_value(packed) + self.string_offset

    def extension_word(self, word_index: int) -> int:
        """Read an initial extension word; missing words read as zero (§11.1.7)."""
        word_index = index(word_index)
        if word_index < 0:
            raise ValueError("A header extension word index cannot be negative")
        return self._extension[word_index] if word_index < len(self._extension) else 0


def _require_span(name: str, address: int, length: int, limit: int) -> None:
    if address < 64 or address + length > limit:
        raise StoryFormatError(f"{name} at {address:#x} does not fit within {limit:#x} bytes")


def _parse_header(data: bytes) -> StoryHeader:
    if data.startswith(b"FORM"):
        raise StoryFormatError("Blorb containers are not supported yet; supply a raw story file")
    if len(data) < 64:
        raise StoryFormatError("A story must contain the complete 64-byte header")
    version = data[0]
    if not 1 <= version <= 8:
        raise StoryFormatError(f"Unsupported Z-machine version {version}; expected 1-8")

    length_scale = 2 if version <= 3 else 4 if version <= 5 else 8
    file_length = _word(data, 0x1A) * length_scale if version >= 3 else 0
    if version >= 4 and file_length == 0:
        raise StoryFormatError("V4-V8 stories must declare a nonzero file length")
    size = file_length or len(data)
    if size < 64:
        raise StoryFormatError("Declared file length is smaller than the header")
    if size > len(data):
        raise StoryFormatError(f"Truncated story: header declares {size} bytes, found {len(data)}")
    if size > length_scale * 0x10000:
        raise StoryFormatError(f"Story exceeds the V{version} size limit")

    static_memory = _word(data, 0x0E)
    if not 64 <= static_memory <= min(size, 0x10000):
        raise StoryFormatError("Static memory base must follow the header and fit in the story")
    high_memory = _word(data, 0x04)
    _require_span("High memory", high_memory, 1, size)
    # Some historical games put code below the high-memory mark, or even set
    # that mark below static memory. Do not use it as an access boundary.
    _require_span("Dictionary", _word(data, 0x08), 1, min(size, 0x10000))
    _require_span("Object defaults", _word(data, 0x0A), 62 if version <= 3 else 126, static_memory)
    _require_span("Globals table", _word(data, 0x0C), 480, static_memory)

    abbreviations = _word(data, 0x18) if version >= 2 else None
    if abbreviations:
        _require_span(
            "Abbreviations table", abbreviations, 64 if version == 2 else 192, min(size, 0x10000)
        )
    alphabet = _word(data, 0x34) if version >= 5 else None
    if alphabet:
        _require_span("Alphabet table", alphabet, 78, min(size, 0x10000))
    extension_address = _word(data, 0x36) if version >= 5 else None
    extension = ()
    if extension_address:
        _require_span("Header extension", extension_address, 2, min(size, 0x10000))
        extension_size = 2 * (_word(data, extension_address) + 1)
        _require_span("Header extension", extension_address, extension_size, min(size, 0x10000))
        extension = tuple(
            _word(data, offset)
            for offset in range(extension_address, extension_address + extension_size, 2)
        )

    header = StoryHeader(
        version=version,
        release=_word(data, 0x02),
        serial=data[0x12:0x18].decode("ascii", errors="replace") if version >= 2 else None,
        flags1=data[0x01],
        flags2=_word(data, 0x10),
        high_memory=high_memory,
        static_memory=static_memory,
        initial_value=_word(data, 0x06),
        dictionary=_word(data, 0x08),
        object_table=_word(data, 0x0A),
        globals_table=_word(data, 0x0C),
        abbreviations_table=abbreviations,
        file_length=file_length or None,
        checksum=_word(data, 0x1C) if file_length else None,
        routine_offset=8 * _word(data, 0x28) if version in (6, 7) else 0,
        string_offset=8 * _word(data, 0x2A) if version in (6, 7) else 0,
        alphabet_table=alphabet,
        extension_table=extension_address,
        _extension=extension,
    )
    _require_span("Entry point", header.entry_address, 1, size)
    return header


@dataclass(frozen=True, slots=True, init=False)
class Story:
    """An immutable raw story image and validated V1-V8 header.

    Loading checks structural bounds, not executable code or every table entry.
    A checksum mismatch is reported by verify_checksum(), not rejected at load.
    """

    data: bytes = field(repr=False)
    header: StoryHeader

    def __init__(self, data: bytes | bytearray | memoryview) -> None:
        """Copy a byte buffer and validate it; never retain a mutable input view."""
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("Story data must be a bytes-like object")
        data = bytes(data)
        header = _parse_header(data)
        object.__setattr__(self, "data", data)
        object.__setattr__(self, "header", header)

    @classmethod
    def from_file(cls, path: str | PathLike[str]) -> "Story":
        """Read a regular file, detecting its version from its header, not name."""
        path = Path(path)
        if not S_ISREG(path.stat().st_mode):
            raise ValueError(f"Game path is not a regular file: {path}")
        return cls(path.read_bytes())

    @property
    def size(self) -> int:
        """Return the memory image size, excluding declared trailing padding."""
        return self.header.file_length or len(self.data)

    @property
    def calculated_checksum(self) -> int:
        """Return the 16-bit sum of the story bytes after the header (§15, verify)."""
        return sum(self.data[64 : self.size]) & 0xFFFF

    def verify_checksum(self) -> bool | None:
        """Check original bytes (§15, verify), or return None if unavailable.

        V1, V2, and early V3 stories lack the necessary fields. A stored zero
        checksum with a known length is a real checksum and is still checked.
        """
        if self.header.checksum is None:
            return None
        return self.calculated_checksum == self.header.checksum
