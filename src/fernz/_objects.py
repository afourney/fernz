"""V3 object entries, tree links, and properties (Standard §12)."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cached_property

from ._errors import ExecutionError
from ._memory import Memory
from ._text import Text


@dataclass(frozen=True, slots=True)
class Location:
    """Legacy immutable location value; queries now return the richer ZObject."""

    num: int
    name: str


@dataclass(slots=True)
class ZObject:
    """A locally mutable object snapshot, detached from interpreter memory.

    Links are object numbers; zero means no link. Attributes are integer flags
    indexed by attribute number. Properties lists the supplied property numbers
    in descending order, padded to at least 16 entries with zeros for Jericho
    callers. Property values and defaults are not included. Names retain the
    full decoded story text. Lists are ordinary Python lists, not NumPy arrays.
    """

    num: int
    name: str
    parent: int = 0
    sibling: int = 0
    child: int = 0
    attr: list[int] = field(default_factory=lambda: [0] * 32)
    properties: list[int] = field(default_factory=lambda: [0] * 16)


@dataclass(frozen=True, slots=True)
class Property:
    """The number, data address, and byte length of an object property."""

    number: int
    address: int
    size: int


class Objects:
    """Access V3 objects directly in memory, including mutable property tables."""

    max_number = 255

    def __init__(self, memory: Memory) -> None:
        """Bind to the V3 object table."""
        if memory.story.header.version != 3:
            raise NotImplementedError("Object access currently supports V3 only")
        self.memory = memory
        self.base = memory.story.header.object_table

    @cached_property
    def count(self) -> int:
        """Infer the initial table extent using the convention in §12's remarks.

        The standard has no object count. Require contiguous entries ending at
        the earliest property table, and reject layouts that do not satisfy
        that convention. Read the original image: §12.4 allows property table
        pointers to change during play, without changing the object count.
        Opcode operations do not depend on this optional enumeration heuristic.
        """
        data = self.memory.story.data
        cursor = self.base + 62
        boundary = self.memory.story.header.static_memory
        for count in range(1, self.max_number + 1):
            if cursor + 9 > boundary:
                break
            table = int.from_bytes(data[cursor + 7 : cursor + 9], "big")
            if not cursor + 9 <= table < self.memory.story.header.static_memory:
                break
            boundary = min(boundary, table)
            cursor += 9
            if cursor == boundary:
                return count
        raise NotImplementedError("Cannot infer object count from the initial object-table layout")

    def snapshot(self, obj: int) -> ZObject:
        """Read one complete, detached V3 object, without executing or cleaning."""
        properties = [prop.number for prop in self.properties(obj)]
        properties.extend([0] * max(0, 16 - len(properties)))
        return ZObject(
            num=obj,
            name=self.name(obj),
            parent=self.parent(obj),
            sibling=self.sibling(obj),
            child=self.child(obj),
            attr=[int(self.attribute(obj, number)) for number in range(32)],
            properties=properties,
        )

    def _dynamic(self, address: int, size: int) -> int:
        if address < 64 or address + size > self.memory.story.header.static_memory:
            raise ExecutionError(f"Object data at {address:#x} is outside dynamic memory")
        return address

    def _entry(self, obj: int) -> int:
        if not 1 <= obj <= self.max_number:
            raise ExecutionError(f"Invalid V3 object number {obj}")
        return self._dynamic(self.base + 62 + 9 * (obj - 1), 9)

    def parent(self, obj: int) -> int:
        """Return the containing object number."""
        return self.memory.read_byte(self._entry(obj) + 4)

    def sibling(self, obj: int) -> int:
        """Return the next sibling object number."""
        return self.memory.read_byte(self._entry(obj) + 5)

    def child(self, obj: int) -> int:
        """Return the first child object number."""
        return self.memory.read_byte(self._entry(obj) + 6)

    def attribute(self, obj: int, attribute: int, value: bool | None = None) -> bool:
        """Read an attribute, or set it when value is provided."""
        if not 0 <= attribute <= 31:
            raise ExecutionError(f"Invalid V3 attribute {attribute}")
        address = self._entry(obj) + attribute // 8
        mask = 0x80 >> (attribute % 8)
        byte = self.memory.read_byte(address)
        if value is not None:
            byte = byte | mask if value else byte & ~mask
            self.memory.write_byte(address, byte)
        return bool(byte & mask)

    def remove(self, obj: int) -> None:
        """Detach an object from its parent while keeping its children."""
        entry = self._entry(obj)
        parent = self.parent(obj)
        if parent:
            link = self._entry(parent) + 6
            seen = set()
            while (current := self.memory.read_byte(link)) != obj:
                if current == 0 or current in seen:
                    raise ExecutionError(f"Broken sibling chain for object {obj}")
                seen.add(current)
                link = self._entry(current) + 5
            self.memory.write_byte(link, self.sibling(obj))
        self.memory.write_bytes(entry + 4, b"\x00\x00")

    def insert(self, obj: int, destination: int) -> None:
        """Move an object to the head of another object's child list."""
        entry, target = self._entry(obj), self._entry(destination)
        # §12.5 leaves tree validity to the game. Reject cycles when detected.
        ancestor = destination
        seen = {obj}
        while ancestor:
            if ancestor in seen:
                raise ExecutionError("Object insertion would create a cycle")
            seen.add(ancestor)
            ancestor = self.parent(ancestor)
        self.remove(obj)
        self.memory.write_bytes(entry + 4, bytes((destination, self.child(destination))))
        self.memory.write_byte(target + 6, obj)

    def _table(self, obj: int) -> int:
        return self._dynamic(self.memory.read_word(self._entry(obj) + 7), 1)

    def name(self, obj: int) -> str:
        """Decode the bounded short name of an object."""
        table = self._table(obj)
        words = self.memory.read_byte(table)
        self._dynamic(table, 1 + 2 * words)
        return Text(self.memory).decode(table + 1, words=words)

    def properties(self, obj: int) -> Iterator[Property]:
        """Walk the strictly descending property list, checking its bounds."""
        table = self._table(obj)
        address = table + 1 + 2 * self.memory.read_byte(table)
        previous = 32
        while size_byte := self.memory.read_byte(self._dynamic(address, 1)):
            number, size = size_byte & 31, (size_byte >> 5) + 1
            if not 0 < number < previous:
                raise ExecutionError(f"Invalid property order for object {obj}")
            yield Property(number, self._dynamic(address + 1, size), size)
            previous = number
            address += size + 1

    def find(self, obj: int, number: int) -> Property | None:
        """Return a property, or None if the object omits it."""
        if not 1 <= number <= 31:
            raise ExecutionError(f"Invalid V3 property {number}")
        return next((p for p in self.properties(obj) if p.number == number), None)

    def get(self, obj: int, number: int) -> int:
        """Read a one- or two-byte property, falling back to its default."""
        prop = self.find(obj, number)
        if prop is None:
            return self.memory.read_word(self.base + 2 * (number - 1))
        if prop.size not in (1, 2):
            raise ExecutionError(f"get_prop requires a one- or two-byte property: {number}")
        read = self.memory.read_byte if prop.size == 1 else self.memory.read_word
        return read(prop.address)

    def put(self, obj: int, number: int, value: int) -> None:
        """Write an existing one- or two-byte property."""
        prop = self.find(obj, number)
        if prop is None or prop.size not in (1, 2):
            raise ExecutionError(
                f"put_prop requires an existing one- or two-byte property: {number}"
            )
        if prop.size == 1:
            self.memory.write_byte(prop.address, value & 0xFF)
        else:
            self.memory.write_word(prop.address, value)

    def next_property(self, obj: int, number: int) -> int:
        """Return the next property number, or the first when number is zero."""
        properties = iter(self.properties(obj))
        if number:
            for prop in properties:
                if prop.number == number:
                    break
            else:
                raise ExecutionError(f"Missing property {number} of object {obj}")
        prop = next(properties, None)
        return prop.number if prop else 0
