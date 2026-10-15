"""Side-effect-free instruction decoding for V1-V8 (Standard §4)."""

from dataclasses import dataclass
from enum import IntEnum

from ._errors import ExecutionError
from ._memory import Memory, MemoryAccessError
from ._opcodes import Opcode, opcode


class OperandType(IntEnum):
    """The encoded operand type; variables remain unresolved during decoding."""

    LARGE = 0
    SMALL = 1
    VARIABLE = 2


@dataclass(frozen=True, slots=True)
class Operand:
    """A literal value or a variable number, before evaluation."""

    type: OperandType
    value: int


@dataclass(frozen=True, slots=True)
class Branch:
    """A branch condition and signed offset; zero and one mean return."""

    on_true: bool
    offset: int


@dataclass(frozen=True, slots=True)
class Instruction:
    """A decoded instruction, including its full extent and optional suffixes."""

    address: int
    next_address: int
    group: str
    number: int
    opcode: Opcode
    operands: tuple[Operand, ...]
    store: int | None = None
    branch: Branch | None = None
    text_address: int | None = None


def decode_branch(memory: Memory, address: int) -> tuple[Branch, int]:
    """Decode a branch suffix and return its continuation address (§4.7)."""
    value = memory.read_byte(address)
    address += 1
    offset = value & 0x3F
    if not value & 0x40:
        offset = offset << 8 | memory.read_byte(address)
        address += 1
        if offset & 0x2000:
            offset -= 0x4000
    return Branch(bool(value & 0x80), offset), address


def decode(memory: Memory, address: int) -> Instruction:
    """Decode one instruction without reading variables or changing memory."""
    cursor = address

    def byte() -> int:
        nonlocal cursor
        value = memory.read_byte(cursor)
        cursor += 1
        return value

    def word() -> int:
        return byte() << 8 | byte()

    version = memory.story.header.version
    try:
        first = byte()
        types: list[int] = []
        if first == 0xBE and version >= 5:
            group, number = "EXT", byte()
        elif first >= 0xC0:
            group, number = ("VAR" if first & 0x20 else "2OP"), first & 0x1F
        elif first >= 0x80:
            kind = (first >> 4) & 3
            group, number = ("0OP" if kind == 3 else "1OP"), first & 0x0F
            if kind != 3:
                types.append(kind)
        else:
            group, number = "2OP", first & 0x1F
            types = [2 if first & 0x40 else 1, 2 if first & 0x20 else 1]

        if first >= 0xC0 or group == "EXT":
            count = 2 if group == "VAR" and number in (12, 26) else 1
            type_bytes = [byte() for _ in range(count)]
            omitted = False
            for value in type_bytes:
                for shift in (6, 4, 2, 0):
                    kind = (value >> shift) & 3
                    if kind == 3:
                        omitted = True
                    elif omitted:
                        raise ExecutionError(f"Operand after omitted operand at {address:#x}")
                    else:
                        types.append(kind)

        spec = opcode(group, number, version)
        if spec is None:
            if group == "EXT" and number >= 29:
                # §14.2.1: unknown extended opcodes are ignored, including operands.
                spec = Opcode("extended_nop", (0, 4))
            else:
                raise ExecutionError(f"Illegal V{version} opcode {group}:{number} at {address:#x}")
        if not spec.operands[0] <= len(types) <= spec.operands[1]:
            raise ExecutionError(f"Wrong operand count for {spec.name} at {address:#x}")
        operands = tuple(Operand(OperandType(t), word() if t == 0 else byte()) for t in types)
        store = byte() if spec.store else None
        branch = None
        if spec.branch:
            branch, cursor = decode_branch(memory, cursor)
        text_address = None
        if spec.text:
            text_address = cursor
            while not word() & 0x8000:
                pass
        return Instruction(
            address, cursor, group, number, spec, operands, store, branch, text_address
        )
    except MemoryAccessError as exc:
        raise ExecutionError(f"Truncated instruction at {address:#x}: {exc}") from exc
