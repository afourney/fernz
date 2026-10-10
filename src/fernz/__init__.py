"""Fernz package scaffold for a Z-machine interpreter."""

from ._env import FernzEnv

__all__ = ["FernzEnv", "hello"]


def hello() -> str:
    """Return the package scaffold's greeting."""
    return "Hello from fernz!"
