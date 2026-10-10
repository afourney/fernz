"""V3 Z-string, ZSCII, and dictionary encoding (Standard §3)."""

from ._errors import ExecutionError
from ._memory import Memory

_ALPHABETS = (
    "abcdefghijklmnopqrstuvwxyz",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    " \n0123456789.,!?_#'\"/\\-:()",
)
_EXTRA = "äöüÄÖÜß»«ëïÿËÏáéíóúýÁÉÍÓÚÝàèìòùÀÈÌÒÙâêîôûÂÊÎÔÛåÅøØãñõÃÑÕæÆçÇþðÞÐ£œŒ¡¿"


def zscii(code: int) -> str:
    """Translate a V3 output code; reject undefined or input-only characters."""
    if code == 0:
        return ""
    if code == 13:
        return "\n"
    if 32 <= code <= 126:
        return chr(code)
    if 155 <= code < 155 + len(_EXTRA):
        return _EXTRA[code - 155]
    raise ExecutionError(f"Invalid V3 output character {code}")


class Text:
    """Decode live V3 memory without caching strings that games can change."""

    def __init__(self, memory: Memory) -> None:
        """Bind the decoder to a V3 image."""
        if memory.story.header.version != 3:
            raise NotImplementedError("Text decoding currently supports V3 only")
        self.memory = memory

    def encode_input(self, line: str) -> bytes:
        """Lowercase one command line and encode it with the default ZSCII table.

        The host supplies an edited line without a newline. Unsupported Unicode
        and control characters are rejected instead of silently losing input.
        """
        if not isinstance(line, str):
            raise TypeError("An action must be a string")
        result = bytearray()
        for char in line.lower():
            if 32 <= ord(char) <= 126:
                result.append(ord(char))
            elif char in _EXTRA:
                result.append(155 + _EXTRA.index(char))
            else:
                raise ValueError(f"Unsupported V3 input character: {char!r}")
        return bytes(result)

    def encode_dictionary(self, word: bytes) -> bytes:
        """Encode a V3 dictionary key, truncating to six Z-characters (§3.7)."""
        chars: list[int] = []
        for code in word:
            char = chr(code)
            if code == 32:
                chars.append(0)
            elif char in _ALPHABETS[0]:
                chars.append(6 + _ALPHABETS[0].index(char))
            elif char in _ALPHABETS[1]:
                chars.extend((4, 6 + _ALPHABETS[1].index(char)))
            elif code == 13:
                chars.extend((5, 7))
            elif char in _ALPHABETS[2][2:]:
                chars.extend((5, 6 + _ALPHABETS[2].index(char)))
            else:
                chars.extend((5, 6, code >> 5, code & 31))
            if len(chars) >= 6:
                break
        chars = (chars + [5] * 6)[:6]
        first = (chars[0] << 10) | (chars[1] << 5) | chars[2]
        last = 0x8000 | (chars[3] << 10) | (chars[4] << 5) | chars[5]
        return first.to_bytes(2, "big") + last.to_bytes(2, "big")

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
                output.append(zscii(chars[position] << 5 | chars[position + 1]))
                position += 2
            else:
                output.append(_ALPHABETS[alphabet][char - 6])
            alphabet = 0
        return "".join(output)
