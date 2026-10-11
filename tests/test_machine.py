import pytest

from fernz import ExecutionError, Memory, Story, UnsupportedOpcodeError
from fernz._machine import Machine

from .story_files import READ, program_bytes, zchars
from .test_objects import object_memory


def machine(code, *chunks):
    return Machine(Memory(Story(program_bytes(code, *chunks))), seed=17)


def run_hex(code):
    result = machine(bytes.fromhex(code) + READ)
    result.run()
    return result


def test_input_suspends_without_reading_or_advancing_further():
    m = machine(bytes.fromhex("e5 7f 41") + READ + b"\x00")
    before = m.memory.read_bytes(0x280, 64)
    assert m.run() == "A"
    assert m.input_request.text == 0x280
    assert m.input_request.parse == 0x2A0
    assert not m.halted
    assert m.pc == 0x40A
    assert m.memory.read_bytes(0x280, 64) == before
    assert m.run() == ""


def test_input_resumes_once_with_resolved_operands_and_new_output():
    # Read consumes two stack operands once; accept_input must not pop them again.
    m = machine(bytes.fromhex("e8 3f 02 a0 e8 3f 02 80 e4 af 00 00 e5 7f 42") + READ)
    assert m.run() == ""
    assert m.frames[0].stack == []
    pc = m.pc
    m.accept_input("LOOK")
    assert m.pc == pc
    assert m.run() == "\nB"
    assert m.memory.read_bytes(0x281, 5) == b"look\x00"
    assert m.input_request is not None
    assert m.run() == ""


def test_input_requires_a_pending_request():
    m = machine(b"\xba")
    with pytest.raises(ExecutionError, match="not waiting"):
        m.accept_input("look")
    m.run()
    with pytest.raises(ExecutionError, match="not waiting"):
        m.accept_input("look")


def test_quit_stops_before_the_next_instruction():
    m = machine(bytes.fromhex("ba 00"))
    assert m.run() == ""
    assert m.halted
    assert m.input_request is None


@pytest.mark.parametrize(
    "opcode,a,b,expected",
    [
        (20, 65535, 2, 1),
        (21, 0, 1, 65535),
        (22, 0x8000, 2, 0),
        (23, -11, 2, -5),
        (23, -11, -2, 5),
        (23, 11, -2, -5),
        (24, -13, 5, -3),
        (24, 13, -5, 3),
        (24, -13, -5, -3),
        (23, -32768, -1, -32768),
    ],
)
def test_arithmetic_wrap_and_specification_signed_division(opcode, a, b, expected):
    code = (
        bytes((0xC0 | opcode, 0x0F))
        + (a & 0xFFFF).to_bytes(2, "big")
        + (b & 0xFFFF).to_bytes(2, "big")
        + b"\x10"
    )
    m = machine(code + READ)
    m.run()
    assert m.read_variable(16) == expected & 0xFFFF


@pytest.mark.parametrize("opcode", (23, 24))
def test_division_by_zero_has_opcode_and_address(opcode):
    with pytest.raises(ExecutionError, match=r"(div|mod) at 0x401: Division by zero"):
        machine(bytes((opcode, 1, 0, 16))).run()


def test_variable_operands_pop_from_left_to_right():
    m = run_hex("e8 7f 07 e8 7f 0b 75 00 00 10")  # 11 - 7, not 7 - 11.
    assert m.read_variable(16) == 4
    assert not m.frames[0].stack


def test_indirect_sp_read_write_increment_and_pull():
    m = run_hex("e8 7f 01 0d 00 09 95 00 9e 00 10 e8 7f 07 e9 7f 00")
    assert m.read_variable(16) == 10
    assert m.frames[0].stack == [7]


def test_variable_reference_itself_is_evaluated_first():
    m = run_hex("0d 10 11 0d 11 29 a5 10")  # Global16 refers to global17.
    assert m.read_variable(17) == 42


@pytest.mark.parametrize("code", ("b9", "9e 00 10", "95 00", "e9 7f 10", "a5 01", "0d 01 01"))
def test_stack_underflow_and_nonexistent_locals(code):
    with pytest.raises(ExecutionError, match="at 0x401"):
        run_hex(code)


def test_calls_use_defaults_override_arguments_and_restore_caller_stack():
    # Main pushes 9; calls routine(42), storing its result on caller's stack.
    # Routine has defaults 7 and 8, prints local2, pushes 99, returns local1.
    m = machine(
        bytes.fromhex("e8 7f 09 e0 1f 03 80 2a 00") + READ,
        (0x700, bytes.fromhex("02 00 07 00 08 e6 bf 02 e8 7f 63 ab 01")),
    )
    assert m.run() == "8"
    assert len(m.frames) == 1
    assert m.frames[0].stack == [9, 42]


def test_null_call_and_extra_arguments():
    m = run_hex("e0 3f 00 00 10")
    assert m.read_variable(16) == 0
    m = machine(bytes.fromhex("e0 17 03 80 01 02 10") + READ, (0x700, b"\x00\xb0"))
    m.run()
    assert m.read_variable(16) == 1


def test_callee_cannot_pop_callers_stack():
    m = machine(bytes.fromhex("e8 7f 09 e0 3f 03 80 10") + READ, (0x700, b"\x00\xb8"))
    with pytest.raises(ExecutionError, match="stack underflow"):
        m.run()


@pytest.mark.parametrize("branch,expected", [(0xC0, 0), (0xC1, 1), (0x41, 42)])
def test_branch_returns_and_false_branch(branch, expected):
    m = machine(
        bytes.fromhex("e0 3f 03 80 10") + READ, (0x700, bytes((0, 0x90, 0, branch, 0x9B, 42)))
    )
    m.run()
    assert m.read_variable(16) == expected


def test_signed_comparison_and_branch_address_base():
    # jl -1, 1 branches over printing 'X', then print 'Y'.
    m = machine(bytes.fromhex("c2 1f ff ff 01 c5 e5 7f 58 e5 7f 59") + READ)
    assert m.run() == "Y"


def test_backward_branch_and_inc_chk_wrap():
    # Initialize global16=-2; increment and branch back while it is not > 0.
    m = run_hex("cd 4f 10 ff fe 05 10 00 3f fd")
    assert m.read_variable(16) == 1
    m = run_hex("cd 4f 10 7f ff 05 10 00 42")
    assert m.read_variable(16) == 0x8000


def test_print_variants_and_print_ret_return_value():
    m = machine(
        bytes.fromhex("e0 3f 03 80 10 87 06 00 8d 03 00 e6 3f ff ff bb") + READ,
        (0x600, zchars(6, 7, 8)),
        (0x700, b"\x00\xb3" + zchars(9, 10, 11)),
    )
    assert m.run() == "def\nabcabc-1\n"
    assert m.read_variable(16) == 1


def test_array_reads_writes_byte_truncation_and_negative_index():
    m = run_hex(
        "e1 03 02 00 00 01 ab cd cf 0f 02 04 ff ff 10 e2 13 02 00 01 12 34 d0 1f 02 00 01 11"
    )
    assert m.read_variable(16) == 0xABCD
    assert m.read_variable(17) == 0x34


@pytest.mark.parametrize(
    "code,match",
    [
        ("e1 17 03 00 00 01", "read-only"),
        ("cf 0f ff ff 00 00 10", "64 KiB"),
        ("b0", "initial execution context"),
        ("bd c1", "initial execution context"),
    ],
)
def test_invalid_execution_errors(code, match):
    with pytest.raises(ExecutionError, match=match):
        run_hex(code)


def test_random_seed_repeatability_and_range():
    code = bytes.fromhex("e7 3f ff f9 10") + bytes.fromhex("e7 7f 06 00") * 40 + READ
    m = machine(code)
    m.run()
    first = m.frames[0].stack[:]
    assert m.read_variable(16) == 0
    assert all(1 <= n <= 6 for n in first)
    m = Machine(m.memory)
    m.run()
    assert m.frames[0].stack == first


def test_header_capabilities_and_game_write_protection():
    m = machine(READ)
    assert m.memory.read_byte(1) & 0x70 == 0x10
    assert m.memory.read_word(0x32) == 0
    with pytest.raises(ValueError, match="protected header"):
        m.memory.write_byte(1, 0)


def test_unsupported_opcode_is_not_silently_ignored():
    with pytest.raises(UnsupportedOpcodeError, match=r"split_window .*0x401"):
        run_hex("ea 7f 01")


def test_execution_budget_and_exact_budget_boundary():
    with pytest.raises(ExecutionError, match="budget"):
        machine(bytes.fromhex("8c ff ff")).run(max_steps=12)
    assert machine(READ).run(max_steps=1) == ""
    with pytest.raises(ValueError, match="positive"):
        machine(READ).run(max_steps=0)


def test_bitwise_and_multiple_equality_operands():
    m = machine(
        bytes.fromhex("08 aa 0f 10 29 f0 10 11 af 11 12 c1 55 02 01 02 03 c5 e5 7f 58") + READ
    )
    assert m.run() == ""
    assert m.read_variable(16) == 0xAF
    assert m.read_variable(17) == 0xA0
    assert m.read_variable(18) == 0xFF5F


def test_test_and_decrement_branches():
    # test succeeds; dec_chk decrements 0 to -1 and branches below 0.
    m = machine(bytes.fromhex("07 07 03 c5 e5 7f 58 04 10 00 c5 e5 7f 59") + READ)
    assert m.run() == ""
    assert m.read_variable(16) == 0xFFFF


def test_screen_stream_selection_and_zero_window_operations():
    m = machine(
        bytes.fromhex(
            "f3 3f ff ff e5 7f 58 f3 7f 00 f3 7f 01 ea 7f 00 eb 7f 00 f4 7f 00 bc b4 e5 7f 59"
        )
        + READ
    )
    assert m.run() == "Y"


def test_unsigned_byte_array_index_and_address_wrap():
    # In a 64 KiB image, read at 0x8000 and wrap 0xffff+1 to 0.
    data = bytearray(program_bytes(bytes.fromhex("d0 0f 00 00 80 00 10 d0 1f ff ff 01 11") + READ))
    data.extend(bytes(65536 - len(data)))
    data[0x1A:0x1C] = (32768).to_bytes(2, "big")
    data[0x8000] = 42
    m = Machine(Memory(Story(data)))
    m.run()
    assert m.read_variable(16) == 42
    assert m.read_variable(17) == 3


def test_object_opcodes_and_store_before_branch():
    # get_child stores its result even when the existence branch is taken.
    code = (
        bytes.fromhex(
            "92 01 10 c5 e5 7f 58 91 02 11 42 93 02 12 11 01 0a 13 12 01 05 14 13 01 0a 15 94 00 16 8a 00 01"
        )
        + READ
    )
    data = bytearray(object_memory().story.data)
    data[0x401 : 0x401 + len(code)] = code
    m = Machine(Memory(Story(data)))
    assert m.run() == "abc"
    assert [m.read_variable(i) for i in range(16, 23)] == [2, 3, 1, 0x1234, 0, 7, 0]


@pytest.mark.parametrize("branch_on_true", [True, False])
@pytest.mark.parametrize(
    "obj,parent,contained",
    [
        (0, 0, True),
        (0, 1, False),
        (0, 65535, False),
        (1, 0, True),
        (1, 1, False),
        (2, 0, False),
        (2, 1, True),
        (2, 3, False),
    ],
)
def test_jin_zero_and_real_objects(obj, parent, contained, branch_on_true):
    # Large operands cover the whole word range; either branch polarity skips
    # only the X marker. Y proves execution continues after either outcome.
    code = b"\xc6\x0f" + obj.to_bytes(2, "big") + parent.to_bytes(2, "big")
    code += bytes((0xC5 if branch_on_true else 0x45,))
    code += bytes.fromhex("e5 7f 58 e5 7f 59") + READ
    data = bytearray(object_memory().story.data)
    data[0x401 : 0x401 + len(code)] = code
    m = Machine(Memory(Story(data)))
    before = m.memory.read_bytes(0x40, 0x240)
    assert m.run() == ("Y" if contained == branch_on_true else "XY")
    assert m.input_request is not None
    assert m.memory.read_bytes(0x40, 0x240) == before


@pytest.mark.parametrize("obj", [256, 65535])
def test_jin_still_rejects_invalid_nonzero_objects(obj):
    code = b"\xc6\x0f" + obj.to_bytes(2, "big") + b"\x00\x00\xc2"
    with pytest.raises(ExecutionError, match="jin at 0x401: Invalid V3 object number"):
        machine(code + READ).run()


def test_get_parent_treats_object_zero_as_parentless():
    m = machine(bytes.fromhex("93 00 10") + READ)
    m.run()
    assert m.memory.read_word(m.memory.story.header.globals_table) == 0


def test_execution_reloads_modified_instructions():
    # Rewrite a dynamic-memory quit into sread, then jump into the changed code.
    code = bytes.fromhex("e2 17 02 40 00 e4 8c fe 38")
    m = machine(code, (0x240, b"\xba" + READ[1:]))
    m.run()
    assert m.input_request is not None
    assert m.pc == 0x246


@pytest.mark.parametrize(
    "code", ["93 00 10", "92 00 10 c2", "91 00 10 c2", "11 00 01 10", "12 00 01 10", "13 00 00 10"]
)
def test_absent_object_reads_return_zero_without_mutation(code):
    m = machine(bytes.fromhex(code) + READ)
    before = m.memory.read_bytes(0x40, 0xC0)
    m.run()
    assert m.read_variable(16) == 0
    assert m.memory.read_bytes(0x40, 0xC0) == before


def test_absent_object_writes_are_noops():
    m = machine(bytes.fromhex("0b 00 1f 0c 00 1f 99 00") + READ)
    before = m.memory.read_bytes(0x40, 0x240)
    m.run()
    assert m.memory.read_bytes(0x40, 0x240) == before


def test_print_absent_object_uses_legacy_name_pointer():
    # The default-property word immediately before object 1 holds the pointer.
    m = machine(
        bytes.fromhex("9a 00") + READ, (0x7C, b"\x02\x00"), (0x200, b"\x01" + zchars(6, 7, 8))
    )
    assert m.run() == "abc"


@pytest.mark.parametrize("push,expected", [(b"", 23), (bytes.fromhex("e8 7f 2a"), 42)])
def test_ret_popped_uses_stack_then_last_local(push, expected):
    # call 0x500, storing the result in global 16; two initial local values.
    m = machine(
        bytes.fromhex("e0 3f 02 80 10") + READ,
        (0x500, bytes.fromhex("02 00 0b 00 17") + push + b"\xb8"),
    )
    m.run()
    assert m.read_variable(16) == expected
    assert len(m.frames) == 1 and not m.frames[0].stack


def test_silent_sound_host_continues_execution():
    m = machine(
        bytes.fromhex("f5 7f 01 f5 5f 03 01 f5 53 03 02 00 08 f5 5f 03 03 f5 5f 03 04 e5 7f 41")
        + READ
    )
    assert m.run() == "A"
    assert m.input_request is not None


def test_print_absent_object_without_name_uses_numeric_placeholder():
    m = machine(bytes.fromhex("9a 00") + READ, (0x7C, b"\x02\x00"))
    assert m.run() == "object#0"
