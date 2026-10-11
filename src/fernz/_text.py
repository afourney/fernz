"""Z-string, ZSCII, and dictionary encoding for V3 and later (Standard §3)."""

from ._errors import ExecutionError
from ._memory import Memory

_ALPHABETS = (
    "abcdefghijklmnopqrstuvwxyz",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    " \n0123456789.,!?_#'\"/\\-:()",
)
_EXTRA = "äöüÄÖÜß»«ëïÿËÏáéíóúýÁÉÍÓÚÝàèìòùÀÈÌÒÙâêîôûÂÊÎÔÛåÅøØãñõÃÑÕæÆçÇþðÞÐ£œŒ¡¿"


def zscii(code: int) -> str:
    """Translate V3 output, with a legacy tab extension for plain transcripts."""
    if code == 0:
        return ""
    if code == 9:
        # Zork I uses tabs although §3.8.2.3 only defines them for V6.
        # Three spaces match black-box Jericho transcript observations. This
        # V3 compatibility rule does not implement V6's contextual indentation.
        return "   "
    if code == 13:
        return "\n"
    if 32 <= code <= 126:
        return chr(code)
    if 155 <= code < 155 + len(_EXTRA):
        return _EXTRA[code - 155]
    raise ExecutionError(f"Invalid V3 output character {code}")


class Text:
    """Decode live memory without caching strings that games can change."""

    def __init__(self, memory: Memory) -> None:
        """Bind the decoder to the story's character and dictionary formats."""
        if memory.story.header.version < 3:
            raise NotImplementedError("Text decoding requires V3 or later")
        self.memory = memory
        self.key_chars = 6 if memory.story.header.version == 3 else 9

    def _extra(self) -> str:
        header = self.memory.story.header
        extension = header.extension_table
        if extension and self.memory.read_word(extension) >= 3:
            table = self.memory.read_word(extension + 6)
            if table:
                count = self.memory.read_byte(table)
                if count > 97:
                    raise ExecutionError("Unicode translation table exceeds 97 characters")
                return "".join(chr(self.memory.read_word(table + 1 + 2 * i)) for i in range(count))
        return _EXTRA

    def character(self, code: int) -> str:
        """Translate one ZSCII output code using the story's Unicode table."""
        if 155 <= code <= 251:
            extra = self._extra()
            if code - 155 < len(extra):
                return extra[code - 155]
            raise ExecutionError(f"Undefined ZSCII output character {code}")
        return zscii(code)

    def _alphabets(self) -> tuple[str, str, str]:
        address = self.memory.story.header.alphabet_table
        if not address:
            return _ALPHABETS
        rows = []
        for row in range(3):
            rows.append(
                "".join(
                    " "
                    if row == 2 and i == 0
                    else "\n"
                    if row == 2 and i == 1
                    else self.character(self.memory.read_byte(address + row * 26 + i))
                    for i in range(26)
                )
            )
        return tuple(rows)

    def encode_output(self, text: str) -> bytes:
        """Convert stream-3 output to ZSCII, replacing unrepresentable Unicode."""
        extra = self._extra()
        return bytes(
            13
            if char == "\n"
            else ord(char)
            if 32 <= ord(char) <= 126
            else 155 + extra.index(char)
            if char in extra
            else 63
            for char in text
        )

    def encode_input(self, line: str, *, lowercase: bool = True) -> bytes:
        """Encode edited input with the story's ZSCII table, optionally lowercasing.

        The host supplies an edited line without a newline. Unsupported Unicode
        and control characters are rejected instead of silently losing input.
        """
        if not isinstance(line, str):
            raise TypeError("An action must be a string")
        result = bytearray()
        extra = self._extra()
        for char in line.lower() if lowercase else line:
            if 32 <= ord(char) <= 126:
                result.append(ord(char))
            elif char in extra:
                result.append(155 + extra.index(char))
            else:
                raise ValueError(f"Unsupported input character: {char!r}")
        return bytes(result)

    def encode_dictionary(self, word: bytes) -> bytes:
        """Encode a dictionary key, truncating to six or nine Z-characters (§3.7)."""
        chars: list[int] = []
        alphabets = self._alphabets()
        for code in word:
            char = self.character(code)
            if code == 32:
                chars.append(0)
            elif char in alphabets[0]:
                chars.append(6 + alphabets[0].index(char))
            elif char in alphabets[1]:
                chars.extend((4, 6 + alphabets[1].index(char)))
            elif code == 13:
                chars.extend((5, 7))
            elif char in alphabets[2][2:]:
                chars.extend((5, 6 + alphabets[2].index(char)))
            else:
                chars.extend((5, 6, code >> 5, code & 31))
            if len(chars) >= self.key_chars:
                break
        chars = (chars + [5] * self.key_chars)[: self.key_chars]
        words = [
            (chars[i] << 10) | (chars[i + 1] << 5) | chars[i + 2]
            for i in range(0, self.key_chars, 3)
        ]
        words[-1] |= 0x8000
        return b"".join(word.to_bytes(2, "big") for word in words)

    def decode(self, address: int, *, words: int | None = None, abbreviation: bool = False) -> str:
        """Read a string, optionally bounded by an object's short-name length."""
        if words == 0:
            return ""
        chars = []
        count = 0
        while True:
            if words is not None and count >= words:
                raise ExecutionError(f"Unterminated object name at {address:#x}")
            value = self.memory.read_word(address + 2 * count)
            chars.extend(((value >> 10) & 31, (value >> 5) & 31, value & 31))
            count += 1
            if value & 0x8000:
                break

        output = []
        alphabets = self._alphabets()
        alphabet = 0
        position = 0
        while position < len(chars):
            char = chars[position]
            position += 1
            if char == 0:
                output.append(" ")
            elif char in (1, 2, 3):
                if abbreviation:
                    raise ExecutionError("An abbreviation cannot contain another abbreviation")
                if position == len(chars):
                    break  # §3.6.1 permits incomplete constructions in ordinary strings.
                table = self.memory.story.header.abbreviations_table
                if not table:
                    raise ExecutionError("String uses an abbreviation without a table")
                entry = 32 * (char - 1) + chars[position]
                position += 1
                target = 2 * self.memory.read_word(table + 2 * entry)
                output.append(self.decode(target, abbreviation=True))
            elif char in (4, 5):
                alphabet = char - 3
                continue
            elif alphabet == 2 and char == 6:
                if position + 1 >= len(chars):
                    if abbreviation:
                        raise ExecutionError("Incomplete character escape in abbreviation")
                    break
                output.append(self.character(chars[position] << 5 | chars[position + 1]))
                position += 2
            else:
                output.append(alphabets[alphabet][char - 6])
            alphabet = 0
        return "".join(output)
