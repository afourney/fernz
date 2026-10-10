"""Instruction layouts from Standard 1.1 §§14-15; no execution behavior."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Opcode:
    """The version-specific trailing fields and operand limits of an opcode."""

    name: str
    operands: tuple[int, int]
    store: bool = False
    branch: bool = False
    text: bool = False


def opcode(group: str, number: int, version: int) -> Opcode | None:
    """Look up a standard opcode, returning None for an illegal encoding."""
    return _TABLE.get((group, number, version))


_TABLE: dict[tuple[str, int, int], Opcode] = {}


def _define(
    group: str,
    number: int,
    name: str,
    operands: int | tuple[int, int],
    first: int = 1,
    last: int = 8,
    *,
    store: bool = False,
    branch: bool = False,
    text: bool = False,
) -> None:
    limits = (operands, operands) if isinstance(operands, int) else operands
    spec = Opcode(name, limits, store, branch, text)
    for version in range(first, last + 1):
        _TABLE[group, number, version] = spec


for _number, _name in enumerate(
    (
        "je",
        "jl",
        "jg",
        "dec_chk",
        "inc_chk",
        "jin",
        "test",
        "or",
        "and",
        "test_attr",
        "set_attr",
        "clear_attr",
        "store",
        "insert_obj",
        "loadw",
        "loadb",
        "get_prop",
        "get_prop_addr",
        "get_next_prop",
        "add",
        "sub",
        "mul",
        "div",
        "mod",
    ),
    start=1,
):
    _define(
        "2OP",
        _number,
        _name,
        (2, 4) if _number == 1 else 2,
        store=_number in (8, 9) or 15 <= _number <= 24,
        branch=1 <= _number <= 7 or _number == 10,
    )
_define("2OP", 25, "call_2s", 2, 4, store=True)
_define("2OP", 26, "call_2n", 2, 5)
_define("2OP", 27, "set_colour", 2, 5)
_define("2OP", 27, "set_colour", (2, 3), 6, 6)
_define("2OP", 28, "throw", 2, 5)

for _number, _name in enumerate(
    (
        "jz",
        "get_sibling",
        "get_child",
        "get_parent",
        "get_prop_len",
        "inc",
        "dec",
        "print_addr",
        "call_1s",
        "remove_obj",
        "print_obj",
        "ret",
        "jump",
        "print_paddr",
        "load",
        "not",
    )
):
    _define(
        "1OP",
        _number,
        _name,
        1,
        4 if _number == 8 else 1,
        store=_number in (1, 2, 3, 4, 8, 14, 15),
        branch=_number in (0, 1, 2),
    )
_define("1OP", 15, "call_1n", 1, 5)

for _number, _name in enumerate(
    (
        "rtrue",
        "rfalse",
        "print",
        "print_ret",
        "nop",
        "save",
        "restore",
        "restart",
        "ret_popped",
        "pop",
        "quit",
        "new_line",
    )
):
    if _number not in (5, 6):
        _define("0OP", _number, _name, 0, text=_number in (2, 3))
for _number, _name in ((5, "save"), (6, "restore")):
    _define("0OP", _number, _name, 0, 1, 3, branch=True)
    _define("0OP", _number, _name, 0, 4, 4, store=True)
_define("0OP", 9, "catch", 0, 5, store=True)
# §15 recommends treating show_status as nop after V3 (Wishbringer compatibility).
_define("0OP", 12, "show_status", 0, 3)
_define("0OP", 13, "verify", 0, 3, branch=True)
_define("0OP", 15, "piracy", 0, 5, branch=True)

_define("VAR", 0, "call", (1, 4), store=True)
_define("VAR", 0, "call_vs", (1, 4), 4, store=True)
for _number, _name in ((1, "storew"), (2, "storeb"), (3, "put_prop")):
    _define("VAR", _number, _name, 3)
_define("VAR", 4, "sread", 2, 1, 3)
_define("VAR", 4, "sread", (2, 4), 4, 4)
_define("VAR", 4, "aread", (2, 4), 5, store=True)
_define("VAR", 5, "print_char", 1)
_define("VAR", 6, "print_num", 1)
_define("VAR", 7, "random", 1, store=True)
_define("VAR", 8, "push", 1)
_define("VAR", 9, "pull", 1)
_define("VAR", 9, "pull", (0, 1), 6, 6, store=True)
_define("VAR", 10, "split_window", 1, 3)
_define("VAR", 11, "set_window", 1, 3)
_define("VAR", 12, "call_vs2", (1, 8), 4, store=True)
_define("VAR", 13, "erase_window", 1, 4)
_define("VAR", 14, "erase_line", 1, 4)
_define("VAR", 15, "set_cursor", 2, 4)
_define("VAR", 15, "set_cursor", (1, 3), 6, 6)
_define("VAR", 16, "get_cursor", 1, 4)
_define("VAR", 17, "set_text_style", 1, 4)
_define("VAR", 18, "buffer_mode", 1, 4)
# §15 and §7 allow memory stream 3 from V3 (the §14 table omits its table operand).
_define("VAR", 19, "output_stream", (1, 2), 3)
_define("VAR", 19, "output_stream", (1, 3), 6, 6)
_define("VAR", 20, "input_stream", 1, 3)
_define("VAR", 21, "sound_effect", (0, 4), 3)
_define("VAR", 22, "read_char", (1, 3), 4, store=True)
_define("VAR", 23, "scan_table", (3, 4), 4, store=True, branch=True)
_define("VAR", 24, "not", 1, 5, store=True)
_define("VAR", 25, "call_vn", (1, 4), 5)
_define("VAR", 26, "call_vn2", (1, 8), 5)
_define("VAR", 27, "tokenise", (2, 4), 5)
_define("VAR", 28, "encode_text", 4, 5)
_define("VAR", 29, "copy_table", 3, 5)
_define("VAR", 30, "print_table", (2, 4), 5)
_define("VAR", 31, "check_arg_count", 1, 5, branch=True)

_define("EXT", 0, "save", (0, 4), 5, store=True)
_define("EXT", 1, "restore", (0, 4), 5, store=True)
_define("EXT", 2, "log_shift", 2, 5, store=True)
_define("EXT", 3, "art_shift", 2, 5, store=True)
_define("EXT", 4, "set_font", 1, 5, store=True)
_define("EXT", 4, "set_font", (1, 2), 6, 6, store=True)
_define("EXT", 5, "draw_picture", (1, 3), 6, 6)
_define("EXT", 6, "picture_data", 2, 6, 6, branch=True)
_define("EXT", 7, "erase_picture", (1, 3), 6, 6)
_define("EXT", 8, "set_margins", (2, 3), 6, 6)
_define("EXT", 9, "save_undo", 0, 5, store=True)
_define("EXT", 10, "restore_undo", 0, 5, store=True)
_define("EXT", 11, "print_unicode", 1, 5)
_define("EXT", 12, "check_unicode", 1, 5, store=True)
_define("EXT", 13, "set_true_colour", 2, 5)
_define("EXT", 13, "set_true_colour", (2, 3), 6, 6)
_define("EXT", 16, "move_window", 3, 6, 6)
_define("EXT", 17, "window_size", 3, 6, 6)
_define("EXT", 18, "window_style", (2, 3), 6, 6)
_define("EXT", 19, "get_wind_prop", 2, 6, 6, store=True)
_define("EXT", 20, "scroll_window", 2, 6, 6)
_define("EXT", 21, "pop_stack", (1, 2), 6, 6)
_define("EXT", 22, "read_mouse", 1, 6, 6)
_define("EXT", 23, "mouse_window", 1, 6, 6)
_define("EXT", 24, "push_stack", 2, 6, 6, branch=True)
_define("EXT", 25, "put_wind_prop", 3, 6, 6)
_define("EXT", 26, "print_form", 1, 6, 6)
_define("EXT", 27, "make_menu", 2, 6, 6, branch=True)
_define("EXT", 28, "picture_table", 1, 6, 6)
_define("EXT", 29, "buffer_screen", 1, 6, 6, store=True)
