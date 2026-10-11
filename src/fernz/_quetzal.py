"""V3/V5/V8 saved games from Quetzal 1.4, independent of host checkpoints."""

from dataclasses import dataclass
from struct import iter_unpack

from ._state import FrameState
from ._story import Story


class SaveFormatError(ValueError):
    """A saved game is malformed, unsupported, or belongs to another story."""


@dataclass(frozen=True, slots=True)
class SavedGame:
    """Portable VM state; PC addresses save's branch or result-variable byte."""

    ram: bytes
    frames: tuple[FrameState, ...]
    pc: int


def _identity(story: Story) -> bytes:
    data = story.data
    checksum = story.header.checksum
    if checksum is None:
        checksum = sum(data[64 : story.size]) & 0xFFFF
    return data[2:4] + data[0x12:0x18] + checksum.to_bytes(2, "big")


def _chunk(name: bytes, data: bytes) -> bytes:
    return name + len(data).to_bytes(4, "big") + data + b"\x00" * (len(data) % 2)


def _compress(ram: bytes, original: bytes) -> bytes:
    delta = bytes(a ^ b for a, b in zip(ram, original, strict=True)).rstrip(b"\x00")
    result = bytearray()
    position = 0
    while position < len(delta):
        if delta[position]:
            result.append(delta[position])
            position += 1
        else:
            end = position + 1
            while end < min(position + 256, len(delta)) and delta[end] == 0:
                end += 1
            result.extend((0, end - position - 1))
            position = end
    return bytes(result)


def _decompress(data: bytes, original: bytes) -> bytes:
    result = bytearray(original)
    position = cursor = 0
    while cursor < len(data):
        value = data[cursor]
        cursor += 1
        if value:
            if position >= len(result):
                raise SaveFormatError("Compressed memory exceeds dynamic memory")
            result[position] ^= value
            position += 1
        else:
            if cursor == len(data):
                raise SaveFormatError("Incomplete compressed-memory run")
            position += data[cursor] + 1
            cursor += 1
        if position > len(result):
            raise SaveFormatError("Compressed memory exceeds dynamic memory")
    return bytes(result)


def dumps(story: Story, state: SavedGame) -> bytes:
    """Encode IFhd, compressed dynamic memory, and oldest-first stack frames."""
    if story.header.version not in (3, 5, 8):
        raise SaveFormatError("Saved-game execution currently supports V3, V5 and V8")
    stack = bytearray()
    for number, frame in enumerate(state.frames):
        if len(frame.stack) > 0xFFFF:
            raise SaveFormatError("A saved evaluation stack exceeds 65535 words")
        # Quetzal §4.11 requires a zeroed dummy header for the initial context.
        stack.extend((frame.return_address or 0).to_bytes(3, "big"))
        flags = len(frame.locals) | (0x10 if number and frame.store is None else 0)
        stack.extend((flags, frame.store or 0, (1 << frame.argument_count) - 1))
        stack.extend(len(frame.stack).to_bytes(2, "big"))
        for value in (*frame.locals, *frame.stack):
            stack.extend(value.to_bytes(2, "big"))
        if number == 0 and stack[:6] != b"\x00" * 6:
            raise SaveFormatError("Invalid initial frame")
    header = _identity(story) + state.pc.to_bytes(3, "big")
    original = story.data[: story.header.static_memory]
    body = b"IFZS" + _chunk(b"IFhd", header)
    body += _chunk(b"CMem", _compress(state.ram, original)) + _chunk(b"Stks", bytes(stack))
    return _chunk(b"FORM", body)


def _frames(data: bytes, story: Story) -> tuple[FrameState, ...]:
    frames = []
    cursor = 0
    while cursor < len(data):
        if cursor + 8 > len(data):
            raise SaveFormatError("Truncated stack frame header")
        pc = int.from_bytes(data[cursor : cursor + 3], "big")
        flags, store, arguments = data[cursor + 3 : cursor + 6]
        count = int.from_bytes(data[cursor + 6 : cursor + 8], "big")
        cursor += 8
        # Quetzal §4: bit 4 discards a result; bits 0..3 count locals. V3 calls
        # always store and take up to three arguments, later calls up to seven.
        early = story.header.version == 3
        argument_masks = (0, 1, 3, 7) if early else (0, 1, 3, 7, 15, 31, 63, 127)
        if flags & (0xF0 if early else 0xE0) or arguments not in argument_masks:
            raise SaveFormatError(f"Invalid V{story.header.version} frame flags or argument mask")
        locals_count = flags & 15
        end = cursor + 2 * (locals_count + count)
        if end > len(data):
            raise SaveFormatError("Truncated locals or evaluation stack")
        words = tuple(word for (word,) in iter_unpack(">H", data[cursor:end]))
        if not frames:
            if pc or flags or store or arguments:
                raise SaveFormatError("Invalid initial frame")
            frame = FrameState((), words, None, None)
        else:
            if not 0 < pc <= story.size:
                raise SaveFormatError("Saved return address is outside the story")
            result = None if flags & 0x10 else store
            if result is not None and 0 < result < 16 and result > len(frames[-1].locals):
                raise SaveFormatError("Saved return refers to a missing caller local")
            frame = FrameState(
                words[:locals_count], words[locals_count:], pc, result, arguments.bit_count()
            )
        frames.append(frame)
        cursor = end
    if not frames:
        raise SaveFormatError("Missing initial frame")
    return tuple(frames)


def loads(story: Story, data: bytes) -> SavedGame:
    """Read a V3/V5/V8 Quetzal file without changing a running game.

    Accept compressed or uncompressed memory, skip unknown chunks, and use the
    first occurrence of each required component (Quetzal §8.8). All sizes are
    checked against the supplied bytes before reading or expanding data.
    """
    if story.header.version not in (3, 5, 8):
        raise SaveFormatError("Saved-game execution currently supports V3, V5 and V8")
    if not isinstance(data, bytes):
        raise TypeError("A restore handler must return bytes or None")
    if len(data) < 12 or data[:4] != b"FORM" or data[8:12] != b"IFZS":
        raise SaveFormatError("Expected a Quetzal FORM/IFZS file")
    if int.from_bytes(data[4:8], "big") != len(data) - 8:
        raise SaveFormatError("Incorrect FORM length")
    pc = ram = frames = None
    cursor = 12
    while cursor < len(data):
        if cursor + 8 > len(data):
            raise SaveFormatError("Truncated chunk header")
        name = data[cursor : cursor + 4]
        size = int.from_bytes(data[cursor + 4 : cursor + 8], "big")
        start, end = cursor + 8, cursor + 8 + size
        cursor = end + size % 2
        if cursor > len(data):
            raise SaveFormatError("Truncated chunk or padding")
        payload = data[start:end]
        if name == b"IFhd" and pc is None:
            if size < 13 or payload[:10] != _identity(story):
                raise SaveFormatError("Saved game belongs to a different story or lacks IFhd data")
            pc = int.from_bytes(payload[10:13], "big")
            if not 0 < pc < story.size:
                raise SaveFormatError("Saved PC is outside the story")
        elif name in (b"CMem", b"UMem", b"Stks"):
            if pc is None:
                raise SaveFormatError("IFhd must precede saved memory and stacks")
            if name == b"Stks" and frames is None:
                frames = _frames(payload, story)
            elif name in (b"CMem", b"UMem") and ram is None:
                original = story.data[: story.header.static_memory]
                ram = _decompress(payload, original) if name == b"CMem" else payload
                if len(ram) != len(original):
                    raise SaveFormatError("Saved memory has the wrong length")
    if pc is None or ram is None or frames is None:
        raise SaveFormatError("Missing IFhd, memory, or Stks chunk")
    return SavedGame(ram, frames, pc)
