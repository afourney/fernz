"""Dictionary lookup and versioned input buffers (Standard §§3.7, 13, 15 read)."""

from ._errors import ExecutionError
from ._memory import Memory
from ._text import Text


class Dictionary:
    """Read a sorted or explicitly unsorted dictionary from live story memory."""

    def __init__(self, memory: Memory, address: int = 0) -> None:
        """Read and validate the dictionary header and entry bounds."""
        self.memory = memory
        self.text = Text(memory)
        alternate = bool(address)
        address = address or memory.story.header.dictionary
        count = memory.read_byte(address)
        self.separators = memory.read_bytes(address + 1, count)
        self.entry_length = memory.read_byte(address + count + 1)
        self.count = memory.read_word(address + count + 2)
        self.sorted = not (alternate and bool(self.count & 0x8000))
        if not self.sorted:
            self.count = 0x10000 - self.count
        self.entries = address + count + 4
        self.key_size = 4 if memory.story.header.version <= 3 else 6
        if self.entry_length < self.key_size:
            minimum = "four" if self.key_size == 4 else "six"
            raise ExecutionError(f"Dictionary entries must contain at least {minimum} bytes")
        end = self.entries + self.count * self.entry_length
        if end > min(len(memory), 0x10000):
            raise ExecutionError("Dictionary entries extend outside byte-addressable memory")

    def lookup(self, word: bytes) -> int:
        """Return an entry's byte address, or zero for an unrecognized word."""
        key = self.text.encode_dictionary(word)
        if not self.sorted:
            for i in range(self.count):
                address = self.entries + i * self.entry_length
                if self.memory.read_bytes(address, self.key_size) == key:
                    return address
            return 0
        low, high = 0, self.count - 1
        while low <= high:
            middle = (low + high) // 2
            address = self.entries + middle * self.entry_length
            entry = self.memory.read_bytes(address, self.key_size)
            if entry == key:
                return address
            if entry < key:
                low = middle + 1
            else:
                high = middle - 1
        return 0

    def parse(
        self,
        text: bytes,
        limit: int,
        *,
        position_base: int,
        skip_unknown: bool = False,
        existing: bytes = b"",
    ) -> bytes:
        """Build a parse count and records, with positions relative to the buffer."""
        records = bytearray()
        position = 0
        while position < len(text) and len(records) // 4 < limit:
            if text[position] == 32:
                position += 1
                continue
            start = position
            if text[position] in self.separators:
                position += 1
            else:
                while (
                    position < len(text)
                    and text[position] != 32
                    and text[position] not in self.separators
                ):
                    position += 1
            address = self.lookup(text[start:position])
            if skip_unknown and not address:
                records.extend(existing[len(records) : len(records) + 4])
            else:
                records.extend(address.to_bytes(2, "big"))
                records.extend((position - start, (position_base + start) & 0xFF))
        return bytes((len(records) // 4,)) + records


def _check_buffer(memory: Memory, address: int, data: bytes) -> None:
    end = min(memory.story.header.static_memory, 0x10000)
    if address < 64 or address + 1 + len(data) > end:
        raise ExecutionError(f"Input buffer at {address:#x} extends outside dynamic memory")


def tokenise(
    memory: Memory,
    text_buffer: int,
    parse_buffer: int,
    dictionary: int = 0,
    skip_unknown: bool = False,
) -> None:
    """Tokenize counted V5 text, preserving unrecognized slots when requested."""
    text = memory.read_bytes(text_buffer + 2, memory.read_byte(text_buffer + 1))
    limit = memory.read_byte(parse_buffer)
    existing = memory.read_bytes(parse_buffer + 2, 4 * limit) if skip_unknown else b""
    parsed = Dictionary(memory, dictionary).parse(
        text, limit, position_base=2, skip_unknown=skip_unknown, existing=existing
    )
    _check_buffer(memory, parse_buffer, parsed)
    memory.write_bytes(parse_buffer + 1, parsed)


def read_line(memory: Memory, text_buffer: int, parse_buffer: int, line: str) -> None:
    """Complete input, validating both buffer writes before changing memory."""
    text = Text(memory).encode_input(line)
    capacity = memory.read_byte(text_buffer)
    early = memory.story.header.version <= 4
    if early and capacity < 2:
        raise ExecutionError("The V3/V4 text buffer must contain at least three bytes")
    if not early and capacity < 1:
        raise ExecutionError("The V5 text buffer must contain at least three bytes")
    if early:
        text = text[: capacity - 1]
        text_data = text + b"\x00"
    else:
        used = memory.read_byte(text_buffer + 1)
        if used > capacity:
            raise ExecutionError("Initial input exceeds the text buffer capacity")
        text = memory.read_bytes(text_buffer + 2, used) + text[: capacity - used]
        text_data = bytes((len(text),)) + text
    writes = [(text_buffer, text_data)]
    if early or parse_buffer:
        words = memory.read_byte(parse_buffer)
        if words < 1:
            raise ExecutionError("The parse buffer must contain at least six bytes")
        parsed = Dictionary(memory).parse(text, words, position_base=1 if early else 2)
        writes.append((parse_buffer, parsed))
    # Check actual writes: some early games overstate their parse-buffer capacity.
    for address, data in writes:
        _check_buffer(memory, address, data)
    if len(writes) == 2 and max(text_buffer, parse_buffer) < min(
        text_buffer + 1 + len(text_data), parse_buffer + 1 + len(writes[1][1])
    ):
        raise ExecutionError("Text and parse buffers overlap")
    # Stage writes as well as bounds: a buffer may overlap a protected header
    # extension, and rejecting the second write must not leave partial input.
    staged = memory.copy()
    for address, data in writes:
        staged.write_bytes(address + 1, data)
    for address, data in writes:
        memory.write_bytes(address + 1, data)
