"""Bounds-checked story memory and game-write permissions (Standard §§1, 11)."""

from operator import index

from ._story import Story


class MemoryAccessError(ValueError):
    """A memory access is out of bounds or changes protected memory."""


class Memory:
    """Independent, mutable memory initialized from an immutable Story.

    Reads use absolute byte addresses and may access the whole image, including
    code and strings above 64 KiB. Future opcodes must enforce their own address
    modes. Writes follow game permissions: dynamic memory only, with protected
    header bits and header-extension words. Values are unsigned and never wrap.
    """

    def __init__(self, story: Story) -> None:
        """Create memory without altering the story image or its header."""
        self._story = story
        self._data = bytearray(story.data[: story.size])

    @property
    def story(self) -> Story:
        """Return the original, immutable story supplying this memory."""
        return self._story

    def __len__(self) -> int:
        """Return the addressable image length, excluding file padding."""
        return len(self._data)

    def _span(self, address: int, length: int) -> tuple[int, int]:
        address, length = index(address), index(length)
        if address < 0 or length < 0 or address + length > len(self):
            raise MemoryAccessError(f"Access at {address:#x} of length {length} is outside memory")
        return address, address + length

    def read_byte(self, address: int) -> int:
        """Read an unsigned byte; negative indices are not supported."""
        start, _ = self._span(address, 1)
        return self._data[start]

    def read_word(self, address: int) -> int:
        """Read an unsigned big-endian word, including at an odd address."""
        start, _ = self._span(address, 2)
        return (self._data[start] << 8) | self._data[start + 1]

    def read_bytes(self, address: int, length: int) -> bytes:
        """Read a copy of a range, never a mutable view into protected memory."""
        start, end = self._span(address, length)
        return bytes(self._data[start:end])

    def write_byte(self, address: int, value: int) -> None:
        """Write a value in 0-255, applying game-write permissions."""
        value = index(value)
        if not 0 <= value <= 0xFF:
            raise ValueError("A byte must be an unsigned 8-bit integer")
        self.write_bytes(address, bytes((value,)))

    def write_word(self, address: int, value: int) -> None:
        """Write a value in 0-65535 atomically, in big-endian byte order."""
        value = index(value)
        if not 0 <= value <= 0xFFFF:
            raise ValueError("A word must be an unsigned 16-bit integer")
        self.write_bytes(address, value.to_bytes(2, "big"))

    def write_bytes(self, address: int, data: bytes | bytearray | memoryview) -> None:
        """Validate an entire write before changing memory; never partially write."""
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("Memory data must be a bytes-like object")
        data = bytes(data)
        start, end = self._span(address, len(data))
        if not data:
            return
        header = self.story.header
        if end > header.static_memory:
            raise MemoryAccessError(f"Write at {start:#x} reaches read-only memory")
        extension_start = header.extension_table or 0
        extension_end = extension_start + 2 * (header.extension_word(0) + 1)
        for offset, value in enumerate(data, start):
            if offset >= 64 and not (extension_start and extension_start <= offset < extension_end):
                continue
            allowed = 0
            if offset == 0x11:
                allowed = 0x01 if header.version <= 2 else 0x03
                if header.version == 6:
                    # Games may acknowledge a redraw request by clearing bit 2.
                    allowed |= self._data[offset] & 0x04
            if (self._data[offset] ^ value) & ~allowed:
                raise MemoryAccessError(f"Write changes protected header bits at {offset:#x}")
        self._data[start:end] = data

    def reset(self) -> None:
        """Restore the original image exactly, including the initial header.

        This is a memory reset, not the VM's restart/restore operation, which
        will also manage interpreter header fields, flags, stack, and CPU state.
        """
        self._data[:] = self.story.data[: self.story.size]

    def _configure_v3_header(self) -> None:
        # Interpreter-only writes (§11), deliberately unavailable to game opcodes.
        # Plain transcript output: no status line, split screen, or variable font.
        self._data[1] = (self._data[1] & ~0x70) | 0x10
        self._data[0x11] &= ~1  # No file transcript is open.
        self._data[0x32:0x34] = b"\x00\x00"  # Do not claim full Standard conformance.

    def _configure_header(self) -> None:
        if self.story.header.version == 3:
            self._configure_v3_header()
            return
        # A fixed-width 80x25 text host. Do not advertise colour, graphics,
        # styles, timed input, mouse, sound, or undo support that is absent.
        self._data[1] = (self._data[1] & 0x62) | 0x10
        flags = self.read_word(0x10) & ~0x01B9
        self._data[0x10:0x12] = flags.to_bytes(2, "big")
        self._data[0x1E:0x28] = bytes((6, ord("F"), 25, 80, 0, 80, 0, 25, 1, 1))
        self._data[0x2C:0x2E] = bytes((2, 9))  # Black background, white foreground.
        # V5 uses Standard 1.0 text semantics, including nested stream 3.
        # Stories use this field to select their text-capture implementation.
        self._data[0x32:0x34] = b"\x01\x00"

    def _restore_dynamic(self, data: bytes) -> None:
        # Validate against the configured header before touching live memory.
        # The snapshot includes interpreter-owned header fields; ordinary game
        # writes still cannot change them. Flags 2 is restored with this host
        # checkpoint, unlike the story-level restore opcode (§6.1.2).
        if type(data) is not bytes or len(data) != self.story.header.static_memory:
            raise ValueError("Expected a complete immutable dynamic-memory snapshot")
        candidate = Memory(self.story)
        candidate._configure_header()
        candidate.write_bytes(0, data)
        self._data[: len(data)] = data

    def _prepare_restore(self, data: bytes) -> "Memory":
        # Opcode restoration preserves the current Flags 2 and resets the
        # interpreter-owned Rst fields (§6.1.2, §11), even for foreign saves.
        if len(data) != self.story.header.static_memory:
            raise ValueError("Saved memory has the wrong length")
        candidate = Memory(self.story)
        candidate._configure_header()
        restored = bytearray(data)
        if self.story.header.version == 3:
            restored[1] = (restored[1] & ~0x70) | (candidate._data[1] & 0x70)
        else:
            restored[1] = candidate._data[1]
            restored[0x1E:0x28] = candidate._data[0x1E:0x28]
            restored[0x2C:0x2E] = candidate._data[0x2C:0x2E]
        restored[0x10:0x12] = self._data[0x10:0x12]
        restored[0x32:0x34] = candidate._data[0x32:0x34]
        candidate.write_bytes(0, restored)
        return candidate

    def copy(self) -> "Memory":
        """Copy current memory while sharing only the immutable original Story."""
        result = Memory(self.story)
        result._data[:] = self._data
        return result
