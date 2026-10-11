"""Independent specification examples for the V5 formats and execution model."""

from dataclasses import FrozenInstanceError, replace

import pytest

from fernz import ExecutionError, FernzEnv, Memory, Story, UnsupportedOpcodeError
from fernz._input import Dictionary, read_line, tokenise
from fernz._machine import Machine
from fernz._objects import Objects
from fernz._output import Output
from fernz._state import ExtendedGameState, OutputState, StoredInputRequest
from fernz._text import Text

from .story_files import READ, program_bytes, put_word, zchars

AREAD = READ + b"\x10"


def machine(code, *chunks):
    return Machine(Memory(Story(program_bytes(code, *chunks, version=5))), seed=42)


def test_v5_header_advertises_only_implemented_text_capabilities():
    m = machine(AREAD)
    assert m.memory.read_byte(1) == 0x10
    assert m.memory.read_bytes(0x20, 8) == bytes((25, 80, 0, 80, 0, 25, 1, 1))
    assert m.memory.read_word(0x32) == 0x100
    assert m.memory.story.data[0x20:0x28] == bytes(8)


def test_v5_calls_zero_locals_and_support_seven_arguments():
    # call_vs2 routine(1..7), with an eighth local initialized to zero.
    m = machine(
        bytes.fromhex("ec 15 55 01 80 01 02 03 04 05 06 07 11") + AREAD,
        (0x600, bytes.fromhex("08 e6 bf 08 ff 7f 07 c5 e5 7f 58 ab 07")),
    )
    assert m.run() == "0"
    assert m.read_variable(17) == 7
    assert len(m.frames) == 1


@pytest.mark.parametrize(
    "call", ("8f 01 80", "da 1f 01 80 09", "f9 1f 01 80 09", "fa 1f ff 01 80 09")
)
def test_discarding_calls_leave_caller_stack_and_variables_intact(call):
    m = machine(
        bytes.fromhex("e8 7f 37 0d 11 63 " + call) + AREAD,
        (0x600, bytes.fromhex("01 b0")),
    )
    m.run()
    assert m.frames[0].stack == [55]
    assert m.read_variable(17) == 99


@pytest.mark.parametrize("call", ("8f 00 00", "da 1f 00 00 09", "f9 3f 00 00", "fa 3f ff 00 00"))
def test_discarding_null_calls_do_not_push_a_result(call):
    m = machine(bytes.fromhex(call) + AREAD)
    m.run()
    assert len(m.frames) == 1 and m.frames[0].stack == []


def test_catch_throw_unwinds_to_the_saved_call_frame():
    m = machine(
        bytes.fromhex("88 01 80 11") + AREAD,
        (0x600, bytes.fromhex("01 b9 01 f9 2f 01 a0 01 00")),
        (0x680, bytes.fromhex("01 dc 6f 2a 01 00")),
    )
    m.run()
    assert m.read_variable(17) == 42 and len(m.frames) == 1


def test_counted_input_appends_prefill_omits_zero_and_can_skip_parsing():
    m = machine(AREAD, (0x280, b"\x06\x02go" + b"\xcc" * 6))
    read_line(m.memory, 0x280, 0, " NORTH")
    assert m.memory.read_bytes(0x280, 10) == b"\x06\x06go nor" + b"\xcc\xcc"


def test_aread_resolves_stack_operands_once_and_stores_enter():
    code = bytes.fromhex("e8 3f 02 a0 e8 3f 02 80 e4 af 00 00 00 e6 bf 00") + AREAD
    m = machine(code)
    assert m.run() == "" and m.frames[0].stack == []
    before = m.get_state()
    assert before.input_request.store == 0
    m.accept_input("LOOK")
    assert m.run() == "\n13"
    assert m.memory.read_bytes(0x280, 7) == b"\x14\x04look\x00"
    assert m.memory.read_bytes(0x2A1, 5) == bytes.fromhex("01 00 00 04 02")
    restored = Machine.from_state(Memory(m.memory.story), before)
    restored.accept_input("LOOK")
    assert restored.run() == "\n13"
    assert restored.get_state() == m.get_state()


@pytest.mark.parametrize("action,expected", [("A", 65), ("", 13), ("Ä", 158)])
def test_character_input_preserves_case_without_line_echo(action, expected):
    m = machine(bytes.fromhex("f6 7f 01 11 e6 bf 11") + AREAD)
    m.run()
    assert isinstance(m.input_request, StoredInputRequest) and m.input_request.character
    m.accept_input(action)
    assert m.run() == str(expected)


def test_timed_input_fails_explicitly():
    m = machine(bytes.fromhex("f6 57 01 01 01 10"))
    with pytest.raises(UnsupportedOpcodeError, match="Timed input"):
        m.run()


def test_v5_keys_hold_nine_zcharacters_and_unsorted_alternate_dictionary():
    key = zchars(6, 7, 8, 9, 10, 11, 12, 13, 14)
    memory = machine(AREAD, (0x350, b"\x00\x06\xff\xfe" + key + zchars(*([31] * 9)))).memory
    assert Text(memory).encode_dictionary(b"abcdefghijk") == key
    dictionary = Dictionary(memory, 0x350)
    assert dictionary.lookup(b"abcdefghi") == 0x354
    assert dictionary.lookup(b"zzzzzzzzz") == 0x35A
    assert dictionary.lookup(b"nothing") == 0


def test_tokenise_unknown_words_preserves_slots_and_counted_offsets():
    key = zchars(17, 20, 20, 16, 5, 5, 5, 5, 5)
    memory = machine(
        AREAD,
        (0x280, b"\x14\x08xyz LOOK".lower()),
        (0x2A0, b"\x04\x00" + b"\xaa" * 16),
        (0x350, b"\x00\x06\x00\x01" + key),
    ).memory
    tokenise(memory, 0x280, 0x2A0, 0x350, True)
    assert memory.read_bytes(0x2A1, 9) == b"\x02" + b"\xaa" * 4 + bytes.fromhex("03 54 04 06")


def test_custom_alphabet_and_unicode_translation_are_live():
    data = bytearray(program_bytes(AREAD, version=5))
    put_word(data, 0x34, 0x700)
    alphabets = (
        b"zyxwvutsrqponmlkjihgfedcbaABCDEFGHIJKLMNOPQRSTUVWXYZ\x00\r0123456789.,!?_#'\"/\\-:()"
    )
    data[0x700:0x74E] = alphabets
    put_word(data, 0x36, 0x2D0)
    put_word(data, 0x2D0, 3)
    put_word(data, 0x2D6, 0x780)
    data[0x780:0x783] = b"\x01\x03\xbb"  # ZSCII 155 means lambda.
    data[0x750:0x754] = zchars(6, 7, 5, 6, 4, 27)
    text = Text(Memory(Story(data)))
    assert text.decode(0x750) == "zyλ"
    assert text.encode_dictionary(b"zy") == zchars(6, 7, 5, 5, 5, 5, 5, 5, 5)
    assert text.encode_input("Λ") == b"\x9b"
    assert text.encode_output("λ🙂\n") == b"\x9b?\r"


def object_memory():
    data = bytearray(program_bytes(b"\xba", version=5, size=0x4000))
    for address, value in ((4, 0x2100), (6, 0x2100), (0x0C, 0x1800), (0x0E, 0x2000)):
        put_word(data, address, value)
    data[0x2100] = 0xBA
    first_table = 0x40 + 126 + 300 * 14
    for number in range(300):
        put_word(data, 0x40 + 126 + 14 * number + 12, first_table + 73)
    put_word(data, 0xBE + 12, first_table)
    put_word(data, 0x40 + 2 * 59, 0xABCD)
    properties = b"\x00\xbf\xc0" + bytes(range(64)) + b"\x7e\x12\x34\x21\x56\x00"
    data[first_table : first_table + len(properties)] = properties
    return Memory(Story(data))


def test_v5_objects_have_word_links_48_attributes_and_long_properties():
    objects = Objects(object_memory())
    assert objects.count == 300
    objects.insert(300, 1)
    objects.insert(299, 1)
    assert objects.parent(300) == 1 and objects.sibling(299) == 300
    objects.attribute(300, 47, True)
    assert objects.snapshot(300).attr == [0] * 47 + [1]
    objects.remove(300)
    assert objects.sibling(299) == 0 and objects.parent(300) == 0
    assert [p.number for p in objects.properties(1)] == [63, 62, 33]
    assert objects.find(1, 63).size == 64
    assert objects.property_length(objects.find(1, 63).address) == 64
    assert objects.get(1, 62) == 0x1234 and objects.get(1, 60) == 0xABCD
    assert objects.property_length(objects.find(1, 62).address) == 2
    assert objects.property_length(objects.find(1, 33).address) == 1
    objects.put(1, 33, 0xCAFE)
    assert objects.get(1, 33) == 0xFE
    assert objects.next_property(1, 63) == 62 and objects.next_property(1, 33) == 0
    assert objects.get(1, 63) == 0xC000  # Legacy long-property scalar read.


@pytest.mark.parametrize("version", (3, 5))
def test_nested_memory_output_survives_snapshot_and_ignores_screen_selection(version):
    read = READ if version == 3 else AREAD
    prefix = bytes.fromhex("f3 3f ff ff f3 4f 03 02 40 e5 7f 41 f3 4f 03 02 50 e5 7f 42")
    suffix = bytes.fromhex("f3 3f ff fd e5 7f 43 f3 3f ff fd f3 7f 01 e5 7f 44")
    m = Machine(
        Memory(Story(program_bytes(prefix + read + suffix + read, version=version))), seed=42
    )
    assert m.run() == ""
    state = m.get_state()
    assert isinstance(state, ExtendedGameState)
    for _ in range(2):
        m = Machine.from_state(Memory(m.memory.story), state)
        m.accept_input("x")
        assert m.run() == "D"
        assert m.memory.read_bytes(0x240, 4) == b"\x00\x02AC"
        assert m.memory.read_bytes(0x250, 4) == b"\x00\x02B\r"


def test_memory_output_depth_and_bounds_are_enforced():
    output = Output(machine(AREAD).memory)
    for _ in range(16):
        output.memory_stream(0x240)
    with pytest.raises(ExecutionError, match="16"):
        output.memory_stream(0x240)
    for _ in range(16):
        output.memory_stream(None)
    assert output.state.memory_streams == ()


def test_upper_and_lower_text_share_output_but_keep_separate_cursors():
    output = Output(machine(AREAD).memory)
    assert output.emit("hello") == "hello"
    output.split(2)
    lower = output.state.cursors[0]
    output.select(1)
    output.move(2, 5)
    assert output.emit("clock") == "clock"
    assert output.state.cursors == (lower, (2, 10))
    output.select(0)
    assert output.emit("!") == "!"
    output.select(1)
    assert output.state.cursors[1] == (1, 1)
    output.erase(-1)
    assert output.state == OutputState()


@pytest.mark.parametrize("size,expected", [(4, b"ababcd"), (-4, b"ababab")])
def test_copy_table_overlap_direction(size, expected):
    code = bytes.fromhex("fd 03 02 40 02 42") + (size & 0xFFFF).to_bytes(2, "big") + AREAD
    m = machine(code, (0x240, b"abcdef"))
    m.run()
    assert m.memory.read_bytes(0x240, 6) == expected


@pytest.mark.parametrize(
    "opcode,value,places,result",
    [(2, 0x8000, -1, 0x4000), (3, 0x8000, -1, 0xC000), (2, 0xFFFF, 1, 0xFFFE), (3, 5, -15, 0)],
)
def test_logical_and_arithmetic_shifts(opcode, value, places, result):
    code = (
        bytes((0xBE, opcode, 0x0F))
        + value.to_bytes(2, "big")
        + (places & 0xFFFF).to_bytes(2, "big")
        + b"\x11"
    )
    m = machine(code + AREAD)
    m.run()
    assert m.read_variable(17) == result


def test_extended_snapshot_validation_is_atomic(tmp_path):
    path = tmp_path / "read.z5"
    path.write_bytes(program_bytes(AREAD, version=5))
    env = FernzEnv(path, seed=42)
    env.reset()
    before = env.get_state()
    assert isinstance(before, ExtendedGameState)
    with pytest.raises(FrozenInstanceError):
        before.output.window = 1
    for bad in (
        replace(before, format_version=2),
        replace(before, output=replace(before.output, window=2)),
        replace(before, output=replace(before.output, memory_streams=((0x2FF, 10),))),
        replace(before, input_request=replace(before.input_request, store=256)),
    ):
        with pytest.raises((TypeError, ValueError)):
            env.set_state(bad)
        assert env.get_state() == before


def test_scan_encode_unicode_fonts_and_unavailable_undo():
    # Encode the first nine characters; scan padded word records with stride 3.
    code = bytes.fromhex(
        "fc 14 02 40 09 00 02 50 "
        "f7 45 34 02 70 03 83 11 c5 e5 7f 58 "
        "be 04 7f 04 12 be 04 7f 00 13 "
        "be 0c 3f 03 bb 14 be 0b 3f 03 bb "
        "be 09 ff 15 be 0a ff 16"
    )
    m = machine(code + AREAD, (0x240, b"abcdefghijk"), (0x270, b"\x00\x12!\x00\x34!\x00\x56!"))
    assert m.run() == "λ"
    assert m.memory.read_bytes(0x250, 6) == zchars(6, 7, 8, 9, 10, 11, 12, 13, 14)
    assert [m.read_variable(i) for i in range(17, 23)] == [0x273, 1, 4, 1, 65535, 65535]
    m.display.select(1)
    assert m.display.font(0) == 1
    assert m.display.font(3) == 0
    m.display.select(0)
    assert m.display.font(0) == 4


def test_v5_empty_stack_ret_popped_does_not_use_the_v3_legacy_local():
    m = machine(bytes.fromhex("88 01 80 11") + AREAD, (0x600, b"\x01\xb8"))
    with pytest.raises(ExecutionError, match="underflow"):
        m.run()


def test_v5_save_without_storage_stores_failure():
    m = machine(bytes.fromhex("be 00 ff 11") + AREAD)
    m.run()
    assert m.read_variable(17) == 0
