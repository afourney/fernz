"""A V3 execution core that suspends at the first line-input request."""

from dataclasses import dataclass, field
from operator import index

from ._errors import ExecutionError, UnsupportedOpcodeError
from ._instruction import Instruction, OperandType, decode
from ._memory import Memory, MemoryAccessError
from ._objects import Objects
from ._random import RandomGenerator
from ._text import Text, zscii


def signed(value: int) -> int:
    """Interpret an unsigned word as a signed 16-bit integer."""
    return value - 0x10000 if value & 0x8000 else value


@dataclass(slots=True)
class Frame:
    """A routine's locals and private evaluation stack (§6.3)."""

    locals: list[int] = field(default_factory=list)
    stack: list[int] = field(default_factory=list)
    return_address: int | None = None
    store: int | None = None


@dataclass(frozen=True, slots=True)
class InputRequest:
    """A suspended sread instruction; no input or tokenization has occurred."""

    text: int
    parse: int


class Machine:
    """Execute V3 startup with a bounded instruction budget and captured output."""

    def __init__(self, memory: Memory, *, seed: int | None = None) -> None:
        """Start a fresh episode, resetting memory, frames, output, and randomness."""
        if memory.story.header.version != 3:
            raise NotImplementedError("Story execution currently supports V3 only")
        self.memory = memory
        self.memory.reset()
        self.memory._configure_v3_header()
        self.pc = memory.story.header.entry_address
        self.frames = [Frame()]
        self.text = Text(memory)
        self.objects = Objects(memory)
        self.rng = RandomGenerator(seed)
        self.output: list[str] = []
        self.screen_enabled = True
        self.input_request: InputRequest | None = None
        self.halted = False

    def read_variable(self, number: int, *, indirect: bool = False) -> int:
        """Read a variable, popping sp only for direct reads."""
        if not 0 <= number <= 255:
            raise ExecutionError(f"Invalid variable number {number}")
        frame = self.frames[-1]
        if number == 0:
            if not frame.stack:
                raise ExecutionError("Evaluation stack underflow")
            return frame.stack[-1] if indirect else frame.stack.pop()
        if number < 16:
            if number > len(frame.locals):
                raise ExecutionError(f"Local variable {number} does not exist")
            return frame.locals[number - 1]
        return self.memory.read_word(self.memory.story.header.globals_table + 2 * (number - 16))

    def write_variable(self, number: int, value: int, *, indirect: bool = False) -> None:
        """Write a word, replacing sp in place only for indirect writes."""
        if not 0 <= number <= 255:
            raise ExecutionError(f"Invalid variable number {number}")
        value &= 0xFFFF
        frame = self.frames[-1]
        if number == 0:
            if indirect:
                if not frame.stack:
                    raise ExecutionError("Evaluation stack underflow")
                frame.stack[-1] = value
            else:
                frame.stack.append(value)
        elif number < 16:
            if number > len(frame.locals):
                raise ExecutionError(f"Local variable {number} does not exist")
            frame.locals[number - 1] = value
        else:
            self.memory.write_word(
                self.memory.story.header.globals_table + 2 * (number - 16), value
            )

    def _return(self, value: int) -> None:
        if len(self.frames) == 1:
            raise ExecutionError("Cannot return from the initial execution context")
        frame = self.frames.pop()
        assert frame.return_address is not None
        self.pc = frame.return_address
        if frame.store is not None:
            self.write_variable(frame.store, value)

    def _call(self, packed: int, arguments: list[int], store: int) -> None:
        if packed == 0:
            self.write_variable(store, 0)
            return
        address = self.memory.story.header.unpack_routine_address(packed)
        count = self.memory.read_byte(address)
        if count > 15:
            raise ExecutionError(f"Invalid local count {count} at {address:#x}")
        locals_ = [self.memory.read_word(address + 1 + 2 * i) for i in range(count)]
        for i, value in enumerate(arguments[:count]):
            locals_[i] = value
        self.frames.append(Frame(locals=locals_, return_address=self.pc, store=store))
        self.pc = address + 1 + 2 * count

    def _branch(self, instruction: Instruction, condition: bool) -> None:
        branch = instruction.branch
        assert branch is not None
        if condition == branch.on_true:
            if branch.offset in (0, 1):
                self._return(branch.offset)
            else:
                self.pc += branch.offset - 2

    def _emit(self, text: str) -> None:
        if self.screen_enabled:
            self.output.append(text)

    def _array_address(self, base: int, offset: int, width: int) -> int:
        # Address arithmetic is word arithmetic (§2.3.2), including negative indices.
        address = (base + width * offset) & 0xFFFF
        if address + width > 0x10000:
            raise ExecutionError(f"Array access outside the 64 KiB address space: {address:#x}")
        return address

    def run(self, *, max_steps: int = 250_000) -> str:
        """Run until input or quit; raise instead of looping beyond max_steps."""
        max_steps = index(max_steps)
        if max_steps <= 0:
            raise ValueError("max_steps must be positive")
        for _ in range(max_steps):
            if self.input_request is not None or self.halted:
                break
            instruction = decode(self.memory, self.pc)
            self.pc = instruction.next_address
            try:
                self._execute(instruction)
            except (ExecutionError, MemoryAccessError) as exc:
                raise ExecutionError(
                    f"{instruction.opcode.name} at {instruction.address:#x}: {exc}"
                ) from exc
        if self.input_request is None and not self.halted:
            raise ExecutionError(f"Instruction budget ({max_steps}) exhausted at {self.pc:#x}")
        return "".join(self.output)

    def _execute(self, instruction: Instruction) -> None:
        name = instruction.opcode.name
        # Evaluate from left to right, including variable operands of indirect opcodes.
        args = [
            self.read_variable(o.value) if o.type == OperandType.VARIABLE else o.value
            for o in instruction.operands
        ]

        def store(value: int) -> None:
            assert instruction.store is not None
            self.write_variable(instruction.store, value)

        def branch(condition: bool) -> None:
            self._branch(instruction, condition)

        match name:
            case "rtrue" | "rfalse":
                self._return(int(name == "rtrue"))
            case "ret":
                self._return(args[0])
            case "ret_popped":
                self._return(self.read_variable(0))
            case "call":
                assert instruction.store is not None
                self._call(args[0], args[1:], instruction.store)
            case "jump":
                self.pc += signed(args[0]) - 2
            case "jz":
                branch(args[0] == 0)
            case "je":
                branch(args[0] in args[1:])
            case "jl" | "jg":
                a, b = map(signed, args)
                branch(a < b if name == "jl" else a > b)
            case "inc" | "dec" | "inc_chk" | "dec_chk":
                increment = name.startswith("inc")
                value = (
                    self.read_variable(args[0], indirect=True) + (1 if increment else -1)
                ) & 0xFFFF
                self.write_variable(args[0], value, indirect=True)
                if name.endswith("_chk"):
                    a, b = signed(value), signed(args[1])
                    branch(a > b if increment else a < b)
            case "test":
                branch(args[0] & args[1] == args[1])
            case "or":
                store(args[0] | args[1])
            case "and":
                store(args[0] & args[1])
            case "not":
                store(~args[0])
            case "add":
                store(args[0] + args[1])
            case "sub":
                store(args[0] - args[1])
            case "mul":
                store(args[0] * args[1])
            case "div" | "mod":
                a, b = map(signed, args)
                if b == 0:
                    raise ExecutionError("Division by zero")
                quotient = (abs(a) // abs(b)) * (-1 if (a < 0) != (b < 0) else 1)
                store(quotient if name == "div" else a - quotient * b)
            case "load":
                store(self.read_variable(args[0], indirect=True))
            case "store":
                self.write_variable(args[0], args[1], indirect=True)
            case "push":
                self.write_variable(0, args[0])
            case "pop":
                self.read_variable(0)
            case "pull":
                self.write_variable(args[0], self.read_variable(0), indirect=True)
            case "loadw" | "loadb":
                width = 2 if name == "loadw" else 1
                read = self.memory.read_word if width == 2 else self.memory.read_byte
                store(read(self._array_address(*args, width)))
            case "storew" | "storeb":
                width = 2 if name == "storew" else 1
                address = self._array_address(args[0], args[1], width)
                if width == 2:
                    self.memory.write_word(address, args[2])
                else:
                    self.memory.write_byte(address, args[2] & 0xFF)
            case "get_parent":
                store(self.objects.parent(args[0]))
            case "get_child" | "get_sibling":
                value = (
                    self.objects.child(args[0])
                    if name == "get_child"
                    else self.objects.sibling(args[0])
                )
                store(value)
                branch(value != 0)
            case "jin":
                branch(self.objects.parent(args[0]) == args[1])
            case "test_attr":
                branch(self.objects.attribute(*args))
            case "set_attr" | "clear_attr":
                self.objects.attribute(*args, value=name == "set_attr")
            case "insert_obj":
                self.objects.insert(*args)
            case "remove_obj":
                self.objects.remove(args[0])
            case "get_prop":
                store(self.objects.get(*args))
            case "get_prop_addr":
                prop = self.objects.find(*args)
                store(prop.address if prop else 0)
            case "get_prop_len":
                store((self.memory.read_byte(args[0] - 1) >> 5) + 1 if args[0] else 0)
            case "get_next_prop":
                store(self.objects.next_property(*args))
            case "put_prop":
                self.objects.put(*args)
            case "print" | "print_ret":
                assert instruction.text_address is not None
                self._emit(self.text.decode(instruction.text_address))
                if name == "print_ret":
                    self._emit("\n")
                    self._return(1)
            case "print_addr" | "print_paddr":
                address = (
                    args[0]
                    if name == "print_addr"
                    else self.memory.story.header.unpack_string_address(args[0])
                )
                self._emit(self.text.decode(address))
            case "print_obj":
                self._emit(self.objects.name(args[0]))
            case "print_char":
                self._emit(zscii(args[0]))
            case "print_num":
                self._emit(str(signed(args[0])))
            case "new_line":
                self._emit("\n")
            case "random":
                store(self.rng.random(signed(args[0])))
            case "sread":
                self.input_request = InputRequest(*args)
            case "quit":
                self.halted = True
            case "nop" | "show_status":
                pass  # This transcript interface advertises no status-line display.
            case "verify":
                branch(self.memory.story.verify_checksum() is not False)
            case "output_stream" if signed(args[0]) in (-1, 1):
                self.screen_enabled = signed(args[0]) == 1
            case "output_stream" if args[0] == 0:
                pass
            case "split_window" | "set_window" if args[0] == 0:
                pass  # The only supported window is the unsplit lower window.
            case "input_stream" if args[0] == 0:
                pass
            case _:
                raise UnsupportedOpcodeError(
                    f"Unsupported V3 opcode {name} ({instruction.group}:{instruction.number}) "
                    f"at {instruction.address:#x}"
                )
