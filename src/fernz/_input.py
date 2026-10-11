"""Dictionary lookup and V3 line-input buffers (Standard §§3.7, 13, 15 read)."""

from ._errors import ExecutionError
from ._memory import Memory
from ._text import Text


class Dictionary:
    """Read a V3 sorted dictionary from live story memory."""

    def __init__(self, memory: Memory) -> None:
        """Read and validate the dictionary header and entry bounds."""
        self.memory = memory
        self.text = Text(memory)
        address = memory.story.header.dictionary
        count = memory.read_byte(address)
        self.separators = memory.read_bytes(address + 1, count)
        self.entry_length = memory.read_byte(address + count + 1)
        self.count = memory.read_word(address + count + 2)
        self.entries = address + count + 4
        if self.entry_length < 4:
            raise ExecutionError("V3 dictionary entries must contain at least four bytes")
        end = self.entries + self.count * self.entry_length
        if end > min(len(memory), 0x10000):
            raise ExecutionError("Dictionary entries extend outside byte-addressable memory")

    def lookup(self, word: bytes) -> int:
        """Return an entry's byte address, or zero for an unrecognized word."""
        key = self.text.encode_dictionary(word)
        low, high = 0, self.count - 1
        while low <= high:
            middle = (low + high) // 2
            address = self.entries + middle * self.entry_length
            entry = self.memory.read_bytes(address, 4)
            if entry == key:
                return address
            if entry < key:
                low = middle + 1
            else:
                high = middle - 1
        return 0

    def parse(self, text: bytes, limit: int, *, position_base: int) -> bytes:
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
            records.extend(address.to_bytes(2, "big"))
            records.extend((position - start, position_base + start))
        return bytes((len(records) // 4,)) + records


def read_line(memory: Memory, text_buffer: int, parse_buffer: int, line: str) -> None:
    """Complete V3 input, validating both buffer writes before changing memory."""
    text = Text(memory).encode_input(line)
    capacity = memory.read_byte(text_buffer)
    words = memory.read_byte(parse_buffer)
    if capacity < 2:
        raise ExecutionError("The V3 text buffer must contain at least three bytes")
    if words < 1:
        raise ExecutionError("The parse buffer must contain at least six bytes")
    text = text[: capacity - 1]
    parsed = Dictionary(memory).parse(text, words, position_base=1)
    text_data = text + b"\x00"
    # V3 has no header extension. These buffers must be ordinary dynamic memory.
    # Check actual writes: some early games overstate their parse-buffer capacity.
    end = min(memory.story.header.static_memory, 0x10000)
    for address, data in ((text_buffer, text_data), (parse_buffer, parsed)):
        if address < 64 or address + 1 + len(data) > end:
            raise ExecutionError(f"Input buffer at {address:#x} extends outside dynamic memory")
    if max(text_buffer, parse_buffer) < min(
        text_buffer + 1 + len(text_data), parse_buffer + 1 + len(parsed)
    ):
        raise ExecutionError("Text and parse buffers overlap")
    memory.write_bytes(text_buffer + 1, text_data)
    memory.write_bytes(parse_buffer + 1, parsed)
