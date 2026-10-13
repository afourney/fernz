"""Version-aware object entries, tree links, and properties (Standard §12)."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cached_property

from ._errors import ExecutionError
from ._memory import Memory
from ._profiles import profile_for
from ._text import Text


@dataclass(slots=True)
class ZObject:
    """A locally mutable object snapshot, detached from interpreter memory.

    Links are object numbers; zero means no link. Attributes are integer flags
    indexed by attribute number (32 flags in V3, 48 in V5/V8). Properties lists
    supplied property numbers in encoded order (normally descending), padded
    to at least 16 entries with zeros for Jericho
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
    """Access objects directly in memory, including mutable property tables."""

    def __init__(self, memory: Memory) -> None:
        """Bind to the object layout selected by the story version."""
        self.memory = memory
        self.base = memory.story.header.object_table
        self.early = memory.story.header.version <= 3
        self.max_number = 255 if self.early else 65535
        self.max_property = 31 if self.early else 63
        self.attributes = 32 if self.early else 48
        self.defaults_size = 2 * self.max_property
        self.entry_size = 9 if self.early else 14
        self.link_size = 1 if self.early else 2
        self.link_start = self.attributes // 8
        self.property_offset = self.entry_size - 2
        profile = profile_for(memory.story)
        self._unordered_inspection = (
            profile.unordered_inspection_objects if profile else frozenset()
        )

    @cached_property
    def text(self) -> Text:
        """Return the decoder for object names, created when first needed."""
        return Text(self.memory)

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
        cursor = self.base + self.defaults_size
        boundary = self.memory.story.header.static_memory
        for count in range(1, self.max_number + 1):
            if cursor + self.entry_size > boundary:
                break
            table = int.from_bytes(
                data[cursor + self.property_offset : cursor + self.entry_size], "big"
            )
            if not cursor + self.entry_size <= table < self.memory.story.header.static_memory:
                break
            boundary = min(boundary, table)
            cursor += self.entry_size
            if cursor == boundary:
                return count
        raise NotImplementedError("Cannot infer object count from the initial object-table layout")

    def snapshot(self, obj: int) -> ZObject:
        """Read one complete, detached object, without executing or cleaning."""
        properties = [
            prop.number
            for prop in self.properties(obj, validate_order=obj not in self._unordered_inspection)
        ]
        properties.extend([0] * max(0, 16 - len(properties)))
        return ZObject(
            num=obj,
            name=self.name(obj),
            parent=self.parent(obj),
            sibling=self.sibling(obj),
            child=self.child(obj),
            attr=[int(self.attribute(obj, number)) for number in range(self.attributes)],
            properties=properties,
        )

    def _dynamic(self, address: int, size: int) -> int:
        if address < 64 or address + size > self.memory.story.header.static_memory:
            raise ExecutionError(f"Object data at {address:#x} is outside dynamic memory")
        return address

    def _entry(self, obj: int) -> int:
        if not 1 <= obj <= self.max_number:
            raise ExecutionError(f"Invalid V{self.memory.story.header.version} object number {obj}")
        return self._dynamic(
            self.base + self.defaults_size + self.entry_size * (obj - 1), self.entry_size
        )

    def _read_link(self, address: int) -> int:
        return self.memory.read_byte(address) if self.early else self.memory.read_word(address)

    def _write_link(self, address: int, number: int) -> None:
        self.memory.write_bytes(address, number.to_bytes(self.link_size, "big"))

    def parent(self, obj: int) -> int:
        """Return the containing object number."""
        return self._read_link(self._entry(obj) + self.link_start)

    def sibling(self, obj: int) -> int:
        """Return the next sibling object number."""
        return self._read_link(self._entry(obj) + self.link_start + self.link_size)

    def child(self, obj: int) -> int:
        """Return the first child object number."""
        return self._read_link(self._entry(obj) + self.link_start + 2 * self.link_size)

    def attribute(self, obj: int, attribute: int, value: bool | None = None) -> bool:
        """Read an attribute, or set it when value is provided."""
        if not 0 <= attribute < self.attributes:
            raise ExecutionError(f"Invalid attribute {attribute}")
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
            link = self._entry(parent) + self.link_start + 2 * self.link_size
            seen = set()
            while (current := self._read_link(link)) != obj:
                if current == 0 or current in seen:
                    raise ExecutionError(f"Broken sibling chain for object {obj}")
                seen.add(current)
                link = self._entry(current) + self.link_start + self.link_size
            self._write_link(link, self.sibling(obj))
        self.memory.write_bytes(entry + self.link_start, bytes(2 * self.link_size))

    def insert(self, obj: int, destination: int) -> None:
        """Move an object to the head of another object's child list."""
        entry, target = self._entry(obj), self._entry(destination)
        # §12.5 leaves tree validity to the game. Some stories temporarily
        # introduce a cycle while rearranging objects across several opcodes.
        self.remove(obj)
        self._write_link(entry + self.link_start, destination)
        self._write_link(entry + self.link_start + self.link_size, self.child(destination))
        self._write_link(target + self.link_start + 2 * self.link_size, obj)

    def _table(self, obj: int) -> int:
        return self._dynamic(self.memory.read_word(self._entry(obj) + self.property_offset), 1)

    def name(self, obj: int) -> str:
        """Decode the bounded short name of an object."""
        table = self._table(obj)
        words = self.memory.read_byte(table)
        self._dynamic(table, 1 + 2 * words)
        return self.text.decode(table + 1, words=words)

    def properties(self, obj: int, *, validate_order: bool = True) -> Iterator[Property]:
        """Walk descending properties, allowing legacy V5 duplicates within bounds."""
        table = self._table(obj)
        address = table + 1 + 2 * self.memory.read_byte(table)
        previous = self.max_property + 1
        while size_byte := self.memory.read_byte(self._dynamic(address, 1)):
            number = size_byte & self.max_property
            header_size = 2 if not self.early and size_byte & 0x80 else 1
            if self.early:
                size = (size_byte >> 5) + 1
            elif header_size == 2:
                size = self.memory.read_byte(self._dynamic(address + 1, 1)) & 63 or 64
            else:
                size = 2 if size_byte & 0x40 else 1
            # Several older Inform V5 images repeat a property number. Keep
            # both entries in physical order: lookup/update uses the first,
            # and get_next_prop can return the same number. Increasing lists
            # remain invalid, as do duplicates in the early object format.
            if number == 0 or (
                validate_order and (number > previous or (self.early and number == previous))
            ):
                raise ExecutionError(f"Invalid property order for object {obj}")
            yield Property(number, self._dynamic(address + header_size, size), size)
            previous = number
            address += size + header_size

    def property_length(self, address: int) -> int:
        """Read a property's trailing size byte; address zero has length zero."""
        if address == 0:
            return 0
        size = self.memory.read_byte(address - 1)
        if self.early:
            return (size >> 5) + 1
        if size & 0x80:
            return size & 63 or 64
        return 2 if size & 0x40 else 1

    def find(self, obj: int, number: int) -> Property | None:
        """Return a property, or None if the object omits it."""
        if not 1 <= number <= self.max_property:
            raise ExecutionError(f"Invalid property {number}")
        return next((p for p in self.properties(obj) if p.number == number), None)

    def get(self, obj: int, number: int) -> int:
        """Read a scalar property, with measured legacy V5 long-property behavior."""
        prop = self.find(obj, number)
        if prop is None:
            return self.memory.read_word(self.base + 2 * (number - 1))
        if prop.size not in (1, 2):
            if not self.early:
                # §15 leaves get_prop on long properties undefined. Legacy
                # V5 executable probes return the trailing size byte followed
                # by the first data byte. Acorn Court's parser relies on this.
                return self.memory.read_word(prop.address - 1)
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
        properties = self.properties(obj)
        if number:
            for prop in properties:
                if prop.number == number:
                    break
            else:
                raise ExecutionError(f"Missing property {number} of object {obj}")
        prop = next(properties, None)
        return prop.number if prop else 0
