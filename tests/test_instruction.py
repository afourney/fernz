import pytest

from fernz import ExecutionError, Memory, Story
from fernz._instruction import Branch, Operand, OperandType, decode

from .story_files import program_bytes, story_bytes


def instruction(hex_bytes, version=3):
    memory = Memory(Story(program_bytes(bytes.fromhex(hex_bytes), version=version)))
    before = memory.read_bytes(0, len(memory))
    result = decode(memory, 0x401)
    assert memory.read_bytes(0, len(memory)) == before
    return result


@pytest.mark.parametrize("version", range(1, 9))
def test_specification_long_and_variable_examples(version):
    inst = instruction("05 02 00 d4", version)
    assert inst.opcode.name == "inc_chk"
    assert inst.operands == (Operand(OperandType.SMALL, 2), Operand(OperandType.SMALL, 0))
    assert inst.branch == Branch(True, 20)
    assert inst.next_address == 0x405
    inst = instruction("d6 2f 03 e8 02 00", version)
    assert inst.opcode.name == "mul"
    assert inst.operands == (Operand(OperandType.LARGE, 1000), Operand(OperandType.VARIABLE, 2))
    assert inst.store == 0
    assert inst.next_address == 0x407


@pytest.mark.parametrize(
    "prefix,types", [("14", (1, 1)), ("34", (1, 2)), ("54", (2, 1)), ("74", (2, 2))]
)
def test_long_operand_types_are_not_evaluated(prefix, types):
    inst = instruction(prefix + " 00 00 10")
    assert tuple(o.type for o in inst.operands) == types
    assert inst.next_address == 0x405


@pytest.mark.parametrize(
    "hex_bytes,kind,value", [("8b 12 34", 0, 0x1234), ("9b ff", 1, 255), ("ab 00", 2, 0)]
)
def test_short_form(hex_bytes, kind, value):
    assert instruction(hex_bytes).operands == (Operand(OperandType(kind), value),)


def test_inline_text_extent():
    # The independent example in §4; the following quit is not part of print.
    inst = instruction("b2 11 aa 46 34 16 45 9c a5 ba")
    assert inst.opcode.name == "print"
    assert inst.text_address == 0x402
    assert inst.next_address == 0x40A


@pytest.mark.parametrize(
    "encoding,branch",
    [
        ("c0", Branch(True, 0)),
        ("41", Branch(False, 1)),
        ("bf fe", Branch(True, -2)),
        ("1f ff", Branch(False, 8191)),
        ("a0 00", Branch(True, -8192)),
    ],
)
def test_signed_branches_and_return_offsets(encoding, branch):
    assert instruction("90 00 " + encoding).branch == branch


def test_store_precedes_branch():
    inst = instruction("91 07 10 c1")
    assert inst.store == 16
    assert inst.branch == Branch(True, 1)


def test_v3_memory_stream_layout_from_sections_7_and_15():
    inst = instruction("f3 4f 03 02 00")
    assert inst.opcode.name == "output_stream"
    assert [o.value for o in inst.operands] == [3, 0x200]


def test_sound_effect_without_operands_is_accepted_for_compatibility():
    assert instruction("f5 ff").opcode.name == "sound_effect"


@pytest.mark.parametrize("version", range(1, 9))
def test_version_dependent_store_fields(version):
    old = version <= 4
    inst = instruction("9f 12" + (" 10" if old else ""), version)
    assert inst.opcode.name == ("not" if old else "call_1n")
    assert inst.store == (16 if old else None)
    inst = instruction("b9" + (" 10" if version >= 5 else ""), version)
    assert inst.opcode.name == ("catch" if version >= 5 else "pop")
    assert inst.store == (16 if version >= 5 else None)
    inst = instruction("e4 5f 40 50" + (" 10" if version >= 5 else ""), version)
    assert inst.opcode.name == ("aread" if version >= 5 else "sread")
    assert inst.store == (16 if version >= 5 else None)


@pytest.mark.parametrize("version", range(1, 9))
def test_save_changes_layout_and_becomes_illegal(version):
    if version < 4:
        assert instruction("b5 c1", version).branch == Branch(True, 1)
    elif version == 4:
        assert instruction("b5 10", version).store == 16
    else:
        with pytest.raises(ExecutionError, match="Illegal"):
            instruction("b5", version)


@pytest.mark.parametrize("version", range(4, 9))
def test_double_type_bytes_precede_all_eight_operands(version):
    inst = instruction("ec 15 55 12 34 01 02 03 04 05 06 07 10", version)
    assert [o.value for o in inst.operands] == [0x1234, 1, 2, 3, 4, 5, 6, 7]
    assert inst.store == 16
    assert inst.next_address == 0x40E
    if version >= 5:
        assert instruction("fa 3f ff 12 34", version).store is None


@pytest.mark.parametrize("version", (5, 6, 7, 8))
def test_extended_opcode_and_unknown_extension(version):
    inst = instruction("be 02 5f 08 01 10", version)
    assert inst.opcode.name == "log_shift"
    assert inst.store == 16
    assert inst.next_address == 0x407
    inst = instruction("be 80 7f 01 ba", version)
    assert inst.opcode.name == "extended_nop"
    assert inst.next_address == 0x405
    assert instruction("be 0c 7f 41 10", version).store == 16


@pytest.mark.parametrize("version", (5, 6, 7, 8))
def test_v6_only_layouts_do_not_leak_into_v7_v8(version):
    inst = instruction("e9 ff 10" if version == 6 else "e9 7f 10", version)
    assert inst.store == (16 if version == 6 else None)
    if version == 6:
        assert instruction("be 1d 7f 01 10", version).store == 16
    else:
        assert instruction("be 1d 7f 01", version).store is None
        with pytest.raises(ExecutionError, match="Illegal"):
            instruction("be 05 7f 01", version)


@pytest.mark.parametrize(
    "hex_bytes,version",
    [
        ("be ff", 3),
        ("ec ff ff", 3),
        ("88 00 00 10", 3),
        ("e4 ff", 3),
        ("ec 3f 7f 00 00 01 10", 5),
        ("d4 77 01 02 10", 3),
        ("00 01 02", 3),
    ],
)
def test_illegal_opcode_or_operand_layout(hex_bytes, version):
    with pytest.raises(ExecutionError, match="0x401"):
        instruction(hex_bytes, version)


@pytest.mark.parametrize(
    "hex_bytes",
    [
        "d6 2f 03 e8 02 00",
        "90 00 bf fe",
        "b2 11 aa 80 00",
        "be 02 5f 08 01 10",
        "ec 3f ff 12 34 10",
    ],
)
def test_truncated_instructions(hex_bytes):
    complete = bytes.fromhex(hex_bytes)
    for size in range(1, len(complete)):
        data = bytearray(story_bytes(5))
        data[-size:] = complete[:size]
        with pytest.raises(ExecutionError, match="Truncated"):
            decode(Memory(Story(data)), len(data) - size)
