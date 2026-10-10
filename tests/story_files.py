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
