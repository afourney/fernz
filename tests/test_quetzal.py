from dataclasses import replace

import pytest

from fernz import Memory, Story
from fernz._host_io import HostIO
from fernz._machine import Machine
from fernz._quetzal import SavedGame, SaveFormatError, _compress, _decompress, dumps, loads
from fernz._state import FrameState

from .story_files import READ, program_bytes


def chunk(name, payload):
    # Independent IFF fixture builder: lengths exclude the even-alignment pad.
    return name + len(payload).to_bytes(4, "big") + payload + bytes(len(payload) % 2)


def form(*chunks):
    payload = b"IFZS" + b"".join(chunks)
    return b"FORM" + len(payload).to_bytes(4, "big") + payload


@pytest.fixture
def vector():
    story = Story(program_bytes(bytes.fromhex("b5 c2") + READ))
    header = bytes.fromhex("00 2a") + b"260101" + story.data[0x1C:0x1E] + bytes.fromhex("00 04 02")
    stack = bytes.fromhex(
        "00 00 00 00 00 00 00 02 11 11 22 22 "  # Dummy frame with two stack values.
        "00 04 56 01 10 07 00 01 44 44 55 55"  # Local, three arguments, one stack value.
    )
    return story, header, stack


def test_independent_binary_vector_has_expected_bytes_and_state(vector):
    story, header, stack = vector
    # Only header byte 1 differs: a one-byte zero run, followed by XOR 0x30.
    data = form(chunk(b"IFhd", header), chunk(b"CMem", b"\x00\x00\x30"), chunk(b"Stks", stack))
    memory = Memory(story)
    memory._configure_v3_header()
    expected = SavedGame(
        memory.read_bytes(0, 0x300),
        (
            FrameState((), (0x1111, 0x2222), None, None),
            FrameState((0x4444,), (0x5555,), 0x456, 16, 3),
        ),
        0x402,
    )
    assert loads(story, data) == expected
    assert dumps(story, expected) == data


@pytest.mark.parametrize(
    "delta,encoded",
    [
        (b"\x00" * 10, b""),
        (b"\x01\x02\x03", b"\x01\x02\x03"),
        (b"\x00\x7f\x00\x00", b"\x00\x00\x7f"),
        (b"\x00" * 256 + b"\x80", b"\x00\xff\x80"),
        (b"\x00" * 257 + b"\x80", b"\x00\xff\x00\x00\x80"),
        (b"\x00" * 512 + b"\xff", b"\x00\xff\x00\xff\xff"),
    ],
)
def test_compression_vectors(delta, encoded):
    original = b"\xaa" * len(delta)
    ram = bytes(value ^ 0xAA for value in delta)
    assert _compress(ram, original) == encoded
    assert _decompress(encoded, original) == ram


def test_nonoptimal_compressed_runs_and_omitted_tail_are_accepted():
    original = bytes(range(100))
    assert _decompress(bytes.fromhex("00 03 00 03"), original) == original


@pytest.mark.parametrize("payload", [b"\x00", b"\x00\xff", b"\x01" * 11, b"\x00\x09\x01"])
def test_invalid_compression_is_rejected(payload):
    with pytest.raises(SaveFormatError):
        _decompress(payload, b"\x00" * 10)


def test_uncompressed_memory_unknown_chunks_and_first_occurrence_rules(vector):
    story, header, stack = vector
    chunks = [
        chunk(b"ANNO", b"odd"),
        chunk(b"IFhd", header + b"future extension"),
        chunk(b"IFhd", b"ignored duplicate"),
        chunk(b"UMem", story.data[:0x300]),
        chunk(b"CMem", b"ignored duplicate memory"),
        chunk(b"Stks", stack),
        chunk(b"Stks", b"ignored duplicate stack"),
        chunk(b"IntD", b"ignored interpreter data"),
    ]
    saved = loads(story, form(*chunks))
    assert saved.ram == story.data[:0x300]
    assert saved.pc == 0x402
    assert len(saved.frames) == 2


@pytest.mark.parametrize("field", [0, 2, 8])
def test_wrong_release_serial_or_checksum_is_rejected(vector, field):
    story, header, stack = vector
    header = bytearray(header)
    header[field] ^= 1
    with pytest.raises(SaveFormatError, match="different story"):
        loads(story, form(chunk(b"IFhd", header), chunk(b"CMem", b""), chunk(b"Stks", stack)))


@pytest.mark.parametrize(
    "which,payload",
    [
        (b"IFhd", b"short"),
        (b"UMem", b"short"),
        (b"UMem", b"\x00" * 769),
        (b"Stks", b""),
        (b"Stks", b"\x00" * 7),
        (b"Stks", bytes.fromhex("00 00 00 00 00 00 00 01")),
        (b"Stks", bytes.fromhex("00 00 01 00 00 00 00 00")),
        (b"Stks", bytes.fromhex("00 00 00 00 00 01 00 00")),
    ],
)
def test_invalid_required_chunks_are_rejected(vector, which, payload):
    story, header, stack = vector
    parts = {b"IFhd": header, b"UMem": story.data[:0x300], b"Stks": stack}
    parts[which] = payload
    with pytest.raises(SaveFormatError):
        loads(story, form(*(chunk(key, value) for key, value in parts.items())))


@pytest.mark.parametrize("field,value", [(0, 0xFF), (3, 0x20), (3, 0x10), (4, 1), (5, 2), (5, 15)])
def test_invalid_called_frame_is_rejected(vector, field, value):
    story, header, stack = vector
    stack = bytearray(stack)
    stack[12 + field] = value
    with pytest.raises(SaveFormatError):
        loads(story, form(chunk(b"IFhd", header), chunk(b"CMem", b""), chunk(b"Stks", stack)))


def test_missing_components_bad_container_and_order_are_rejected(vector):
    story, header, stack = vector
    parts = [chunk(b"IFhd", header), chunk(b"CMem", b""), chunk(b"Stks", stack)]
    good = form(*parts)
    invalid = [
        b"",
        b"not a Quetzal file",
        good[:8] + b"BAD!" + good[12:],
        good + b"trailing bytes",
        form(parts[1], parts[0], parts[2]),
        form(*parts, b"short"),
        form(*parts, b"ANNO\x00\x00\x00\x01X"),  # Missing padding.
        form(*parts, b"ANNO\xff\xff\xff\xff"),
        *(form(*parts[:i], *parts[i + 1 :]) for i in range(3)),
    ]
    for data in invalid:
        with pytest.raises(SaveFormatError):
            loads(story, data)


def test_legacy_missing_checksum_is_calculated():
    data = bytearray(program_bytes(bytes.fromhex("b5 c2") + READ))
    data[0x1A:0x1C] = b"\x00\x00"  # Early V3 has neither length nor checksum metadata.
    data[0x1C:0x1E] = b"\x00\x00"
    story = Story(data)
    assert story.header.checksum is None
    state = SavedGame(bytes(data[:0x300]), (FrameState((), (), None, None),), 0x402)
    encoded = dumps(story, state)
    assert int.from_bytes(encoded[28:30], "big") == sum(data[64:]) & 0xFFFF
    assert loads(story, encoded) == state


@pytest.mark.parametrize("version", (3, 5))
@pytest.mark.parametrize("identity", ("valid-zero", "mismatched-zero", "mismatched-nonzero"))
def test_save_identity_preserves_present_checksum_even_when_verification_fails(version, identity):
    code = bytes.fromhex("b5 c2") if version == 3 else bytes.fromhex("be 00 ff 10")
    data = bytearray(
        program_bytes(code + READ + (b"\x10" if version == 5 else b""), version=version)
    )
    stored = 1 if identity == "mismatched-nonzero" else 0
    data[0x1C:0x1E] = stored.to_bytes(2, "big")
    if identity == "valid-zero":
        # Adjust unused static padding so zero is also the correct body sum.
        count, remainder = divmod((-sum(data[64:])) & 0xFFFF, 255)
        data[0x800 : 0x800 + count + 1] = b"\xff" * count + bytes((remainder,))
    story = Story(data)
    assert story.header.checksum == stored
    assert story.verify_checksum() is (identity == "valid-zero")
    state = SavedGame(bytes(data[:0x300]), (FrameState((), (), None, None),), 0x401 + len(code) - 1)
    encoded = dumps(story, state)
    assert int.from_bytes(encoded[28:30], "big") == stored
    assert loads(story, encoded) == state
    if identity != "valid-zero":
        computed = (sum(data[64:]) & 0xFFFF).to_bytes(2, "big")
        with pytest.raises(SaveFormatError, match="different story"):
            loads(story, encoded[:28] + computed + encoded[30:])


@pytest.mark.parametrize("change", ["pc", "branch", "return", "header"])
def test_invalid_continuation_or_header_is_rejected_atomically(vector, change):
    story, _, _ = vector
    ram = bytearray(story.data[:0x300])
    frames = (FrameState((), (), None, None),)
    pc = 0x402
    if change == "pc":
        pc = story.size
    elif change == "branch":
        # Dynamic branch bytes resolving beyond the end of the image.
        pc = 0x250
        ram[pc : pc + 2] = b"\x9f\xff"
    elif change == "return":
        pc = 0x250
        ram[pc] = 0xC1  # Cannot return from the initial context.
    else:
        ram[0] = 5
    data = dumps(story, SavedGame(bytes(ram), frames, pc))
    machine = Machine(Memory(story), seed=17, io=HostIO(restore=lambda: data))
    machine.run()  # No save handler: false branch with offset 2 still reaches READ.
    before = machine.get_state()
    assert not machine._restore()
    assert machine.get_state() == before


def test_restore_adapts_interpreter_header_and_preserves_flags2(vector):
    story, _, _ = vector
    ram = bytearray(story.data[:0x300])
    ram[1] = 0x60
    ram[0x32:0x34] = b"\x01\x01"
    saved = SavedGame(bytes(ram), (FrameState((), (), None, None),), 0x402)
    data = dumps(story, saved)
    machine = Machine(Memory(story), io=HostIO(restore=lambda: data))
    machine.memory.write_byte(0x11, 3)
    assert machine._restore()
    assert machine.memory.read_byte(1) == 0x30
    assert machine.memory.read_word(0x32) == 0
    assert machine.memory.read_word(0x10) == 2


def test_writer_refuses_unrepresentable_evaluation_stack(vector):
    story, _, _ = vector
    state = SavedGame(story.data[:0x300], (FrameState((), (), None, None),), 0x402)
    with pytest.raises(SaveFormatError, match="65535"):
        dumps(story, replace(state, frames=(replace(state.frames[0], stack=(1,) * 65536),)))


def test_saved_branch_can_jump_backwards_into_dynamic_code():
    story = Story(program_bytes(READ, (0x250, READ), (0x260, b"\xbf\xf0")))
    state = SavedGame(story.data[:0x300], (FrameState((), (), None, None),), 0x260)
    data = dumps(story, state)
    machine = Machine(Memory(story), io=HostIO(restore=lambda: data))
    assert machine._restore()
    assert machine.pc == 0x250
    assert machine.run() == ""
    assert machine.input_request.instruction_address == 0x250
