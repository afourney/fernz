"""Small, independently constructed memory images; no interpreter/compiler used."""


def put_word(data: bytearray, address: int, value: int) -> None:
    data[address : address + 2] = value.to_bytes(2, "big")


def story_bytes(version: int = 3, size: int = 4096) -> bytes:
    """Build a structural fixture with empty tables and no executable program."""
    data = bytearray(size)
    data[0] = version
    put_word(data, 0x02, 42)
    put_word(data, 0x04, 0x400)  # High memory.
    put_word(data, 0x06, 0x100 if version == 6 else 0x401)
    put_word(data, 0x08, 0x300)  # Dictionary.
    put_word(data, 0x0A, 0x40)  # Object defaults fit before globals.
    put_word(data, 0x0C, 0x100)  # 240 globals, ending at 0x2e0.
    put_word(data, 0x0E, 0x300)  # Static memory.
    if version >= 2:
        data[0x12:0x18] = b"260101"
    if version >= 3:
        put_word(data, 0x1A, size // {3: 2, 4: 4, 5: 4, 6: 8, 7: 8, 8: 8}[version])
    # Body bytes are zero, so the checksum is zero as well.
    return bytes(data)


READ = bytes.fromhex("e4 0f 02 80 02 a0")  # sread text=0x280, parse=0x2a0.


def program_bytes(
    code: bytes, *chunks: tuple[int, bytes], version: int = 3, size: int = 4096
) -> bytes:
    """Place hand-assembled instructions and data in an independent fixture."""
    data = bytearray(story_bytes(version, size=size))
    data[0x401 : 0x401 + len(code)] = code
    data[0x280] = 20
    data[0x2A0] = 4
    data[0x301] = 4  # Empty, structurally valid V3 dictionary.
    for address, chunk in chunks:
        data[address : address + len(chunk)] = chunk
    if version >= 3:
        put_word(data, 0x1C, sum(data[64:]) & 0xFFFF)
    return bytes(data)


def zchars(*chars: int) -> bytes:
    """Pack explicit Z-characters, padding with 5 and marking the last word."""
    padded = [*chars, *([5] * (-len(chars) % 3))] or [5, 5, 5]
    words = [
        (a << 10) | (b << 5) | c
        for a, b, c in zip(padded[::3], padded[1::3], padded[2::3], strict=True)
    ]
    words[-1] |= 0x8000
    return b"".join(word.to_bytes(2, "big") for word in words)
