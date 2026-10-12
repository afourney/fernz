"""A version-aware execution core that suspends at input requests."""

from copy import copy
from dataclasses import dataclass, field
from hashlib import sha256
from operator import index

from ._errors import ExecutionError, UnsupportedOpcodeError
from ._host_io import HostIO
from ._input import read_line, tokenise
from ._instruction import Branch, Instruction, OperandType, decode, decode_branch
from ._memory import Memory, MemoryAccessError
from ._objects import Objects
from ._output import Output
from ._profiles import profile_for
from ._quetzal import SavedGame, SaveFormatError, dumps, loads
from ._random import RandomGenerator
from ._state import FrameState, GameState, InputRequest, OutputState, StoredInputRequest
from ._text import Text

# Lost Pig can legitimately exceed 250,000 instructions in a single command.
# Keep execution bounded, with headroom for its measured parser/scope searches.
DEFAULT_MAX_STEPS = 1_000_000


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
    """Execute V3/V4/V5/V8 with a bounded instruction budget and captured output."""

    def __init__(
        self,
        memory: Memory,
        *,
        seed: int | None = None,
        io: HostIO | None = None,
        screen_width: int = 80,
        screen_height: int = 25,
    ) -> None:
        """Start a fresh episode, resetting memory, frames, output, and randomness."""
        if memory.story.header.version not in (3, 4, 5, 8):
            raise NotImplementedError("Story execution currently supports V3, V4, V5 and V8")
        self.memory = memory
        self.io = io or HostIO()
        self.memory.reset()
        self.memory._configure_header(screen_width, screen_height)
        self.pc = memory.story.header.entry_address
        self.frames = [Frame()]
        self.text = Text(memory)
        self.objects = Objects(memory)
        self._profile = profile_for(memory.story)
        self.rng = RandomGenerator(seed)
        self.output: list[str] = []
        self._narrative: list[str] = []
        self.last_narrative = ""
        self.screen_enabled = True
        self.display = Output(memory, OutputState(width=screen_width, height=screen_height))
        self.display.start()
        self.last_stream = ""
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
            output=self.display.state,
        )

    def _frame_states(self) -> tuple[FrameState, ...]:
        return tuple(
            FrameState(tuple(f.locals), tuple(f.stack), f.return_address, f.store, f.argument_count)
            for f in self.frames
        )

    @classmethod
    def from_state(cls, memory: Memory, state: GameState, *, io: HostIO | None = None) -> "Machine":
        """Restore a checkpoint, validating everything before changing memory."""
        if memory.story.header.version not in (3, 4, 5, 8):
            raise NotImplementedError("Story execution currently supports V3, V4, V5 and V8")
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
        result._profile = profile_for(memory.story)
        result.rng = RandomGenerator.from_state(state.rng)
        result.output = []  # Public calls already drained the previous observation.
        result._narrative = []
        result.last_narrative = ""
        result.last_stream = ""
        result.screen_enabled = state.screen_enabled
        result.display = Output(memory, state.output)
        result.input_request = state.input_request
        result.halted = state.halted
        memory._restore_dynamic(state.ram, width=result.display.width, height=result.display.height)
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

    def _call(self, packed: int, arguments: list[int], store: int | None) -> None:
        if packed == 0:
            if store is not None:
                self.write_variable(store, 0)
            return
        address = self.memory.story.header.unpack_routine_address(packed)
        count = self.memory.read_byte(address)
        if count > 15:
            raise ExecutionError(f"Invalid local count {count} at {address:#x}")
        defaults = self.memory.story.header.version <= 4
        locals_ = (
            [self.memory.read_word(address + 1 + 2 * i) for i in range(count)]
            if defaults
            else [0] * count
        )
        for i, value in enumerate(arguments[:count]):
            locals_[i] = value
        self.frames.append(
            Frame(
                locals=locals_, return_address=self.pc, store=store, argument_count=len(arguments)
            )
        )
        self.pc = address + 1 + (2 * count if defaults else 0)

    def _branch(self, branch: Branch, condition: bool) -> None:
        if condition == branch.on_true:
            if branch.offset in (0, 1):
                self._return(branch.offset)
            else:
                self.pc += branch.offset - 2

    def _emit(self, text: str) -> None:
        if self.display.state.memory_streams or self.screen_enabled:
            # Stream 3 is independent of whether screen output is enabled.
            text = self.display.emit(text)
        if text and self.screen_enabled:
            self.output.append(text)
            if self.display.state.window == 0:
                self._narrative.append(text)
            if self.io.output is not None:
                self.io.output(text)

    def _save(self, instruction: Instruction) -> bool:
        # Quetzal §5.8: before applying the result, save the branch address in
        # V3 or the store-variable address in V4+. Host checkpoints pause later.
        saved = SavedGame(
            self.memory.read_bytes(0, self.memory.story.header.static_memory),
            self._frame_states(),
            instruction.address + 1
            if self.memory.story.header.version == 3
            else instruction.next_address - 1,
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
            candidate.memory = self.memory._prepare_restore(saved.ram)
            candidate.frames = [
                Frame(list(f.locals), list(f.stack), f.return_address, f.store, f.argument_count)
                for f in saved.frames
            ]
            if self.memory.story.header.version == 3:
                branch, candidate.pc = decode_branch(candidate.memory, saved.pc)
                candidate._branch(branch, True)
            else:
                candidate.pc = saved.pc + 1
                candidate.write_variable(candidate.memory.read_byte(saved.pc), 2)
            if not 0 <= candidate.pc < len(self.memory):
                raise SaveFormatError("Restored continuation is outside the story")
        except (SaveFormatError, MemoryAccessError, ExecutionError):
            return False
        self.memory._restore_dynamic(
            candidate.memory.read_bytes(0, self.memory.story.header.static_memory),
            width=self.display.width,
            height=self.display.height,
        )
        self.frames, self.pc = candidate.frames, candidate.pc
        if self.memory.story.header.version == 3:
            self.display.split(0)
        return True

    def _restart(self) -> None:
        # §6.1.3: restore the original image and interpreter header, retaining
        # Flags 2. Keep the Memory object used by the text/object helpers.
        flags2 = self.memory.read_word(0x10)
        self.memory.reset()
        self.memory._configure_header(self.display.width, self.display.height)
        self.memory.write_word(0x10, flags2)
        self.pc = self.memory.story.header.entry_address
        self.frames = [Frame()]
        self.input_request = None
        self.halted = False
        self.rng.reset()  # §2.4: leave any opcode-seeded predictable sequence.
        # Output already emitted in this turn, stream selection, and host I/O
        # belong to the session. Restart does not discard or replace them.

    def _array_address(self, base: int, offset: int, width: int) -> int:
        # Address arithmetic is word arithmetic (§2.3.2), including negative indices.
        address = (base + width * offset) & 0xFFFF
        if address + width > 0x10000:
            raise ExecutionError(f"Array access outside the 64 KiB address space: {address:#x}")
        return address

    def run(self, *, max_steps: int = DEFAULT_MAX_STEPS) -> str:
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
        self.last_narrative = "".join(self._narrative)
        self._narrative.clear()
        self.last_stream = self.display.drain()
        return output

    def accept_input(self, line: str) -> None:
        """Complete the pending read without re-evaluating its operands."""
        request = self.input_request
        if request is None or self.halted:
            raise ExecutionError("The machine is not waiting for line input")
        try:
            if isinstance(request, StoredInputRequest) and request.character:
                encoded = self.text.encode_input(line, lowercase=False)
                self.write_variable(request.store, encoded[0] if encoded else 13)
            else:
                read_line(self.memory, request.text, request.parse, line)
                if isinstance(request, StoredInputRequest):
                    self.write_variable(request.store, 13)
        except MemoryAccessError as exc:
            raise ExecutionError(f"Invalid input buffer or dictionary: {exc}") from exc
        self.input_request = None
        if not isinstance(request, StoredInputRequest) or not request.character:
            self._emit("\n")  # Line reads print the Enter terminator (§15).

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
                if args:
                    raise UnsupportedOpcodeError("Auxiliary region saves are not implemented")
                success = self._save(instruction)
                if instruction.branch is not None:
                    branch(success)
                else:
                    store(int(success))
            case "restore":
                if args:
                    raise UnsupportedOpcodeError("Auxiliary region restores are not implemented")
                if not self._restore():
                    if instruction.branch is not None:
                        branch(False)
                    else:
                        store(0)
            case "restart":
                self._restart()
            case "rtrue" | "rfalse":
                self._return(int(name == "rtrue"))
            case "ret":
                self._return(args[0])
            case "ret_popped":
                frame = self.frames[-1]
                # Seastalker uses ret_popped with an empty evaluation stack.
                # Executable probes return the last local in this historical
                # case. Keep other stack underflows strict.
                value = (
                    frame.locals[-1]
                    if self.memory.story.header.version == 3 and not frame.stack and frame.locals
                    else self.read_variable(0)
                )
                self._return(value)
            case (
                "call"
                | "call_vs"
                | "call_vs2"
                | "call_1s"
                | "call_2s"
                | "call_1n"
                | "call_2n"
                | "call_vn"
                | "call_vn2"
            ):
                self._call(args[0], args[1:], instruction.store)
            case "check_arg_count":
                branch(self.frames[-1].argument_count >= args[0])
            case "catch":
                store(len(self.frames) - 1)
            case "throw":
                if not 0 < args[1] < len(self.frames):
                    raise ExecutionError("Invalid catch frame token")
                del self.frames[args[1] + 1 :]
                self._return(args[0])
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
                store(self.objects.parent(args[0]) if args[0] else 0)
            case "get_child" | "get_sibling":
                value = (
                    0
                    if not args[0]
                    else (
                        self.objects.child(args[0])
                        if name == "get_child"
                        else self.objects.sibling(args[0])
                    )
                )
                store(value)
                branch(value != 0)
            case "jin":
                # V3 compatibility: treat object zero as parentless for jin only.
                parent = self.objects.parent(args[0]) if args[0] else 0
                branch(parent == args[1])
            case "test_attr":
                # Historical V3 stories also query the absent object. Like
                # jin, this opcode treats zero as empty without dereferencing it.
                branch(self.objects.attribute(*args) if args[0] else False)
            case "set_attr" | "clear_attr":
                ignored = self._profile and args[1] in self._profile.ignored_attribute_writes
                if args[0] and not ignored:
                    self.objects.attribute(*args, value=name == "set_attr")
            case "insert_obj":
                # Legacy games sometimes move to/from the absent object.
                # Public executable probes leave the entire tree unchanged.
                if args[0] and args[1]:
                    self.objects.insert(*args)
            case "remove_obj":
                if args[0]:
                    self.objects.remove(args[0])
            case "get_prop":
                store(self.objects.get(*args) if args[0] else 0)
            case "get_prop_addr":
                # A property above the V3 range cannot be present (§12.4.1).
                prop = (
                    self.objects.find(*args)
                    if args[0] and args[1] <= self.objects.max_property
                    else None
                )
                store(prop.address if prop else 0)
            case "get_prop_len":
                store(self.objects.property_length(args[0]))
            case "get_next_prop":
                store(self.objects.next_property(*args) if args[0] else 0)
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
                if args[0]:
                    self._emit(self.objects.name(args[0]))
                else:
                    # Historical print_obj 0 addresses the word immediately
                    # before object 1 as its name-table pointer. Cutthroats
                    # exercises this on an unresolved pronoun. Keep the text
                    # bounded by the addressable story image in this case.
                    table = self.memory.read_word(
                        self.objects.base + self.objects.defaults_size - 2
                    )
                    self._emit(
                        self.text.decode(table + 1) if self.memory.read_byte(table) else "object#0"
                    )
            case "print_char":
                self._emit(self.text.character(args[0]))
            case "print_num":
                self._emit(str(signed(args[0])))
            case "new_line":
                self._emit("\n")
            case "random":
                store(self.rng.random(signed(args[0])))
            case "sread":
                if len(args) == 4 and all(args[2:]):
                    raise UnsupportedOpcodeError("Timed input is not supported")
                self.input_request = InputRequest(
                    *args[:2], instruction_address=instruction.address
                )
            case "aread" | "read_char":
                timing = args[2:] if name == "aread" else args[1:]
                if len(timing) == 2 and all(timing):
                    raise UnsupportedOpcodeError("Timed input is not supported")
                if name == "read_char" and args[0] != 1:
                    raise ExecutionError("Only keyboard character input is supported")
                assert instruction.store is not None
                self.input_request = StoredInputRequest(
                    text=args[0] if name == "aread" else 0,
                    parse=args[1] if name == "aread" else 0,
                    instruction_address=instruction.address,
                    store=instruction.store,
                    character=name == "read_char",
                )
            case "tokenise":
                tokenise(
                    self.memory, *args[:3], skip_unknown=bool(args[3]) if len(args) > 3 else False
                )
            case "encode_text":
                text, length, start, destination = args
                self.memory.write_bytes(
                    destination,
                    self.text.encode_dictionary(self.memory.read_bytes(text + start, length)),
                )
            case "copy_table":
                source, destination, size = args
                size = signed(size)
                if destination == 0:
                    self.memory.write_bytes(source, bytes(abs(size)))
                elif size >= 0:
                    self.memory.write_bytes(destination, self.memory.read_bytes(source, size))
                else:
                    for offset in range(-size):
                        self.memory.write_byte(
                            destination + offset, self.memory.read_byte(source + offset)
                        )
            case "scan_table":
                value, table, length = args[:3]
                form = args[3] if len(args) == 4 else 0x82
                size = form & 0x7F
                read = self.memory.read_word if form & 0x80 else self.memory.read_byte
                found = next(
                    (table + i * size for i in range(length) if read(table + i * size) == value), 0
                )
                store(found)
                branch(bool(found))
            case "log_shift" | "art_shift":
                value, places = args[0], signed(args[1])
                if not -15 <= places <= 15:
                    raise ExecutionError("Shift count must be between -15 and 15")
                if name == "art_shift":
                    value = signed(value)
                store(value << places if places >= 0 else value >> -places)
            case "save_undo" | "restore_undo":
                store(-1)  # Explicitly unavailable; no undo support is advertised.
            case "quit":
                self.halted = True
            case "nop" | "show_status" | "extended_nop":
                pass  # This transcript interface advertises no status-line display.
            case "sound_effect":
                # Sound resources are external (§9). This text-only host has
                # none to play; preparation, playback and cleanup are silent.
                pass
            case "verify":
                branch(self.memory.story.verify_checksum() is not False)
            case "piracy":
                branch(True)
            case "output_stream" if signed(args[0]) in (-1, 1):
                self.screen_enabled = signed(args[0]) == 1
            case "output_stream" if args[0] == 0:
                pass
            case "output_stream" if signed(args[0]) in (-4, -2, 2, 4):
                # §7.6.5.2: unavailable external streams leave play running.
                # Header writes also keep stream 2's status off (§7.4).
                pass
            case "output_stream" if signed(args[0]) in (-3, 3):
                if args[0] == 3 and len(args) < 2:
                    raise ExecutionError("Memory output requires a table operand")
                self.display.memory_stream(args[1] if args[0] == 3 else None)
            case "split_window":
                self.display.split(args[0])
            case "set_window":
                self.display.select(args[0])
            case "set_cursor":
                self.display.move(*args)
            case "get_cursor":
                row, column = self.display.state.cursors[self.display.state.window]
                self.memory.write_bytes(args[0], row.to_bytes(2, "big") + column.to_bytes(2, "big"))
            case "erase_window":
                self.display.erase(signed(args[0]))
            case "erase_line":
                self.display.erase_line(args[0])
            case "set_text_style":
                self.display.style(args[0])
            case "buffer_mode":
                self.display.buffer(args[0])
            case "set_colour" | "set_true_colour":
                self.display.colour(*map(signed, args), true=name == "set_true_colour")
            case "set_font":
                store(self.display.font(args[0]))
            case "print_unicode":
                self._emit(chr(args[0]))
            case "check_unicode":
                code = args[0]
                printable = 32 <= code <= 0xFFFF and not 0xD800 <= code <= 0xDFFF and code != 127
                readable = printable and (code <= 126 or chr(code) in self.text._extra())
                store(int(printable) | (int(readable) << 1))
            case "print_table":
                table, width = args[:2]
                height = args[2] if len(args) > 2 else 1
                skip = args[3] if len(args) > 3 else 0
                for row in range(height):
                    if row:
                        self._emit("\n")
                    self._emit(
                        "".join(
                            self.text.character(code)
                            for code in self.memory.read_bytes(table + row * (width + skip), width)
                        )
                    )
            case "input_stream" if args[0] in (0, 1):
                # File input is unavailable; continue using host input (§7.6.5.2).
                pass
            case _:
                raise UnsupportedOpcodeError(
                    f"Unsupported V{self.memory.story.header.version} opcode {name} ({instruction.group}:{instruction.number}) "
                    f"at {instruction.address:#x}"
                )
