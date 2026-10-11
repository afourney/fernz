"""A V3 execution core that suspends and resumes at line-input requests."""

from copy import copy
from dataclasses import dataclass, field
from hashlib import sha256
from operator import index

from ._errors import ExecutionError, UnsupportedOpcodeError
from ._host_io import HostIO
from ._input import read_line
from ._instruction import Branch, Instruction, OperandType, decode, decode_branch
from ._memory import Memory, MemoryAccessError
from ._objects import Objects
from ._quetzal import SavedGame, SaveFormatError, dumps, loads
from ._random import RandomGenerator
from ._state import FrameState, GameState, InputRequest
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
    argument_count: int = 0


class Machine:
    """Execute V3 with a bounded instruction budget and captured output."""

    def __init__(
        self, memory: Memory, *, seed: int | None = None, io: HostIO | None = None
    ) -> None:
        """Start a fresh episode, resetting memory, frames, output, and randomness."""
        if memory.story.header.version != 3:
            raise NotImplementedError("Story execution currently supports V3 only")
        self.memory = memory
        self.io = io or HostIO()
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

    def get_state(self) -> GameState:
        """Capture a detached checkpoint at a public input or quit boundary."""
        story = self.memory.story
        return GameState(
            story_sha256=sha256(story.data[: story.size]).hexdigest(),
            ram=self.memory.read_bytes(0, story.header.static_memory),
            pc=self.pc,
            frames=self._frame_states(),
            rng=self.rng.get_state(),
            input_request=self.input_request,
            screen_enabled=self.screen_enabled,
            halted=self.halted,
        )

    def _frame_states(self) -> tuple[FrameState, ...]:
        return tuple(
            FrameState(tuple(f.locals), tuple(f.stack), f.return_address, f.store, f.argument_count)
            for f in self.frames
        )

    @classmethod
    def from_state(cls, memory: Memory, state: GameState, *, io: HostIO | None = None) -> "Machine":
        """Restore a checkpoint, validating everything before changing memory."""
        if memory.story.header.version != 3:
            raise NotImplementedError("Story execution currently supports V3 only")
        if type(state) is not GameState:
            raise TypeError("Expected a GameState returned by get_state()")
        state._validate(memory.story)
        # Construct without the startup/reset side effects of __init__.
        result = cls.__new__(cls)
        result.memory = memory
        result.io = io or HostIO()
        result.pc = state.pc
        result.frames = [
            Frame(list(f.locals), list(f.stack), f.return_address, f.store, f.argument_count)
            for f in state.frames
        ]
        result.text = Text(memory)
        result.objects = Objects(memory)
        result.rng = RandomGenerator.from_state(state.rng)
        result.output = []  # Public calls already drained the previous observation.
        result.screen_enabled = state.screen_enabled
        result.input_request = state.input_request
        result.halted = state.halted
        memory._restore_v3_dynamic(state.ram)
        return result

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
        self.frames.append(
            Frame(
                locals=locals_, return_address=self.pc, store=store, argument_count=len(arguments)
            )
        )
        self.pc = address + 1 + 2 * count

    def _branch(self, branch: Branch, condition: bool) -> None:
        if condition == branch.on_true:
            if branch.offset in (0, 1):
                self._return(branch.offset)
            else:
                self.pc += branch.offset - 2

    def _emit(self, text: str) -> None:
        if self.screen_enabled:
            self.output.append(text)
            if self.io.output is not None:
                self.io.output(text)

    def _save(self, instruction: Instruction) -> bool:
        # A V3 Quetzal PC points to the branch bytes, before save's result is
        # applied. The public checkpoint API has a different suspension point.
        saved = SavedGame(
            self.memory.read_bytes(0, self.memory.story.header.static_memory),
            self._frame_states(),
            instruction.address + 1,
        )
        try:
            data = dumps(self.memory.story, saved)
        except SaveFormatError:
            return False
        return self.io.write_save(data)

    def _restore(self) -> bool:
        data = self.io.read_save()
        if data is None:
            return False
        try:
            saved = loads(self.memory.story, data)
            # Stage only memory, frames, and PC. Branch/return helpers touch
            # those fields alone; RNG, output, and host callbacks stay untouched.
            candidate = copy(self)
            candidate.memory = self.memory._prepare_v3_restore(saved.ram)
            candidate.frames = [
                Frame(list(f.locals), list(f.stack), f.return_address, f.store, f.argument_count)
                for f in saved.frames
            ]
            branch, candidate.pc = decode_branch(candidate.memory, saved.pc)
            candidate._branch(branch, True)
            if not 0 <= candidate.pc < len(self.memory):
                raise SaveFormatError("Restored continuation is outside the story")
        except (SaveFormatError, MemoryAccessError, ExecutionError):
            return False
        self.memory._restore_v3_dynamic(
            candidate.memory.read_bytes(0, self.memory.story.header.static_memory)
        )
        self.frames, self.pc = candidate.frames, candidate.pc
        return True

    def _array_address(self, base: int, offset: int, width: int) -> int:
        # Address arithmetic is word arithmetic (§2.3.2), including negative indices.
        address = (base + width * offset) & 0xFFFF
        if address + width > 0x10000:
            raise ExecutionError(f"Array access outside the 64 KiB address space: {address:#x}")
        return address

    def run(self, *, max_steps: int = 250_000) -> str:
        """Run until input or quit and drain output; enforce an instruction budget."""
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
        output = "".join(self.output)
        self.output.clear()
        return output

    def accept_input(self, line: str) -> None:
        """Complete the pending read without re-evaluating its operands."""
        request = self.input_request
        if request is None or self.halted:
            raise ExecutionError("The machine is not waiting for line input")
        try:
            read_line(self.memory, request.text, request.parse, line)
        except MemoryAccessError as exc:
            raise ExecutionError(f"Invalid input buffer or dictionary: {exc}") from exc
        self.input_request = None
        self._emit("\n")  # The read opcode prints the Enter terminator (§15).

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
            assert instruction.branch is not None
            self._branch(instruction.branch, condition)

        match name:
            case "save":
                branch(self._save(instruction))
            case "restore":
                if not self._restore():
                    branch(False)
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
                self.input_request = InputRequest(*args, instruction_address=instruction.address)
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
