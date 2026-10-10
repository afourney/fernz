"""V3 Z-string and ZSCII output decoding (Standard §3)."""

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
