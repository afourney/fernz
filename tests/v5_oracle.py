"""Independent V5 object records from public RAM and Standard §§3, 12."""

from .v3_oracle import short_name, word
from .v5_corpus_vectors import object_layout


def object_records(data, original):
    assert word(data, 0x34) == 0  # Both trajectory images use the standard alphabets.
    base, count = object_layout(original)
    records = [
        {
            "num": 0,
            "name": "",
            "parent": 0,
            "sibling": 0,
            "child": 0,
            "attr": [0] * 48,
            "properties": [0] * 16,
        }
    ]
    for number in range(1, count + 1):
        entry = base + 14 * (number - 1)
        table = word(data, entry + 12)
        words = data[table]
        cursor = table + 1 + 2 * words
        properties = []
        while data[cursor]:
            header = data[cursor]
            properties.append(header & 63)
            cursor += (
                (2 + (data[cursor + 1] & 63 or 64)) if header & 128 else (3 if header & 64 else 2)
            )
            assert cursor < word(data, 14)
        properties.extend([0] * max(0, 16 - len(properties)))
        records.append(
            {
                "num": number,
                "name": short_name(data, table + 1, words),
                "parent": word(data, entry + 6),
                "sibling": word(data, entry + 8),
                "child": word(data, entry + 10),
                "attr": [(data[entry + bit // 8] >> (7 - bit % 8)) & 1 for bit in range(48)],
                "properties": properties,
            }
        )
    return records


def assert_public_object(obj, record):
    if obj is None or int(obj.num) == 0:
        assert record["name"] == ""
        return
    for field in ("num", "parent", "sibling", "child"):
        assert int(getattr(obj, field)) == record[field], (record["num"], field)
    assert list(obj.attr) == record["attr"][:32]
    assert list(obj.properties) == record["properties"][:16]
