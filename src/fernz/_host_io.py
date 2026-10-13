"""Host callbacks, kept outside both VM saved games and environment checkpoints."""

from collections.abc import Callable
from dataclasses import dataclass

SaveHandler = Callable[[bytes], bool]
RestoreHandler = Callable[[], bytes | None]


@dataclass(frozen=True, slots=True)
class HostIO:
    """Optional storage services supplied by the caller."""

    save: SaveHandler | None = None
    restore: RestoreHandler | None = None

    def __post_init__(self) -> None:
        """Reject invalid handlers before starting execution."""
        for callback in (self.save, self.restore):
            if callback is not None and not callable(callback):
                raise TypeError("I/O handlers must be callable or None")

    def write_save(self, data: bytes) -> bool:
        """Report unavailable storage and OS errors as ordinary save failure."""
        if self.save is None:
            return False
        try:
            success = self.save(data)
        except OSError:
            return False
        if type(success) is not bool:
            raise TypeError("A save handler must return bool")
        return success

    def read_save(self) -> bytes | None:
        """Return file bytes, or None for unavailable, cancelled, or failed input."""
        if self.restore is None:
            return None
        try:
            data = self.restore()
        except OSError:
            return None
        if data is not None and not isinstance(data, bytes):
            raise TypeError("A restore handler must return bytes or None")
        return data
