"""Independent V3 object expectations from public snapshots and Standard §§3, 12.

This recorder deliberately does not use Fernz's object or text implementation.
Only hashes of decoded story text enter the committed vector archives.
"""

A2 = "\0\n0123456789.,!?_#'\"/\\-:()"
EXTENDED = "äöüÄÖÜß»«ëïÿËÏáéíóúýÁÉÍÓÚÝàèìòùÀÈÌÒÙâêîôûÂÊÎÔÛåÅøØãñõÃÑÕæÆçÇþðÞÐ£œŒ¡¿"


def word(data, address):
    if not 0 <= address <= len(data) - 2:
        raise ValueError("Truncated word in reference snapshot")
    return int.from_bytes(data[address : address + 2], "big")


def object_count(data):
    cursor = word(data, 0x0A) + 62
    limit = word(data, 0x0E)
    count = 0
    while cursor < limit:
        limit = min(limit, word(data, cursor + 7))
        cursor += 9
        count += 1
        assert count <= 255 and cursor <= limit
    return count + 1  # Include the empty zero slot.


def short_name(data, address, count, *, depth=0):
    if count == 0:
        return ""
    assert depth < 4, "Recursive abbreviation in the reference story"
    chars = []
    while count is None or len(chars) < count * 3:
        value = word(data, address)
        address += 2
        chars.extend(((value >> 10) & 31, (value >> 5) & 31, value & 31))
        if value & 0x8000:
            break
    result = []
    alphabet = 0
    position = 0
    while position < len(chars):
        char = chars[position]
        position += 1
        if char == 0:
            result.append(" ")
        elif char <= 3:
            abbreviation = 32 * (char - 1) + chars[position]
            position += 1
            table = word(data, 0x18)
            result.append(
                short_name(data, 2 * word(data, table + 2 * abbreviation), None, depth=depth + 1)
            )
        elif char <= 5:
            alphabet = char - 3
            continue
        elif alphabet == 2 and char == 6:
            code = 32 * chars[position] + chars[position + 1]
            position += 2
            if code == 13:
                result.append("\n")
            elif 32 <= code < 127:
                result.append(chr(code))
            elif 155 <= code < 155 + len(EXTENDED):
                result.append(EXTENDED[code - 155])
            else:
                raise ValueError(f"Unexpected object-name ZSCII {code}")
        else:
            result.append(
                ("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ", A2)[alphabet][char - 6]
            )
        alphabet = 0
    return "".join(result)


def object_records(data, count):
    records = [
        {
            "num": 0,
            "name": "",
            "parent": 0,
            "sibling": 0,
            "child": 0,
            "attr": [0] * 32,
            "properties": [0] * 16,
        }
    ]
    base = word(data, 0x0A) + 62
    for number in range(1, count):
        entry = base + 9 * (number - 1)
        table = word(data, entry + 7)
        words = data[table]
        name = short_name(data, table + 1, words)
        cursor = table + 1 + 2 * words
        properties = []
        while data[cursor]:
            size = data[cursor]
            properties.append(size & 31)
            cursor += 2 + (size >> 5)
        properties.extend([0] * max(0, 16 - len(properties)))
        records.append(
            {
                "num": number,
                "name": name,
                "parent": data[entry + 4],
                "sibling": data[entry + 5],
                "child": data[entry + 6],
                "attr": [
                    int(bool(data[entry + bit // 8] & (128 >> (bit % 8)))) for bit in range(32)
                ],
                "properties": properties,
            }
        )
    return records


def assert_public_object(obj, record):
    # Public Jericho names are shortened and unnamed slots are placeholders.
    # Full names come independently from the encoded story text above.
    if obj.num == 0:
        assert record["name"] == ""
        return
    for field in ("num", "parent", "sibling", "child"):
        assert int(getattr(obj, field)) == record[field], (record["num"], field)
    for field in ("attr", "properties"):
        expected = record[field][:16] if field == "properties" else record[field]
        assert list(getattr(obj, field)) == expected, (record["num"], field)
