"""Errors reported by the interpreter, independent of its implementation."""


class ExecutionError(RuntimeError):
    """The story attempted an invalid operation or exceeded the execution budget."""


class UnsupportedOpcodeError(NotImplementedError):
    """A legal instruction is not implemented by this execution engine yet."""
