"""Version-independent random opcode behavior, verified against black-box references."""

import secrets
from operator import index
from random import Random

from ._state import RandomState


def validate_host_seed(seed: int | None) -> int | None:
    """Normalize a host seed without drawing randomness or requesting entropy."""
    if seed is not None:
        seed = index(seed)
        if not 0 <= seed < 2**31:
            raise ValueError("Host seed must be in 0..2**31-1, or None")
    return seed


class RandomGenerator:
    """Use Python randomness or the predictable sequences measured in references.

    Opcode seeds 1-999 select a counting cycle; larger seeds select an affine
    generator. An explicit host seed always selects the affine generator,
    including zero. None selects Python's generator with system entropy.
    See docs/RNG.md for the compatibility contract and black-box reference tests.
    """

    def __init__(self, seed: int | None = None) -> None:
        """Choose a host seed in 0..2**31-1, or request automatic seeding."""
        self._host_seed = validate_host_seed(seed)
        self.reset()

    def reset(self) -> None:
        """Start the host-seeded sequence again, leaving any counting cycle."""
        self._random = Random(secrets.randbits(256)) if self._host_seed is None else None
        self._state = self._host_seed if self._host_seed is not None else 0
        self._period = 0
        self._position = 0

    def get_state(self) -> RandomState:
        """Capture the active generator without advancing or reseeding."""
        return RandomState(
            self._host_seed,
            self._state,
            self._period,
            self._position,
            self._random.getstate() if self._random is not None else None,
        )

    @classmethod
    def from_state(cls, state: RandomState) -> "RandomGenerator":
        """Recreate a generator without requesting entropy or taking a draw."""
        if type(state) is not RandomState:
            raise TypeError("Expected a RandomState")
        state._validate()
        result = cls.__new__(cls)
        result._host_seed = state.host_seed
        result._state = state.state
        result._period = state.period
        result._position = state.position
        result._random = None
        if state.python_state is not None:
            result._random = Random(0)  # An explicit seed avoids requesting entropy.
            result._random.setstate(state.python_state)
        return result

    def random(self, operand: int) -> int:
        """Execute random with a signed word; seeding operations return zero."""
        operand = index(operand)
        if not -32768 <= operand <= 32767:
            raise ValueError("The random operand must be a signed 16-bit integer")
        if operand == 0:
            self.reset()
            return 0
        if operand < 0:
            seed = -operand
            self._random = None
            self._period = seed if seed < 1000 else 0
            self._position = 0
            self._state = seed
            return 0

        if self._random is not None:
            # randrange uses unbiased bounded sampling rather than a remainder.
            return self._random.randrange(1, operand + 1)
        if self._period:
            sample = self._position
            self._position = (self._position + 1) % self._period
        else:
            # Keep a 31-bit state and extract its upper 15 bits for each sample.
            self._state = (22695477 * self._state + 1) % (2**31)
            sample = self._state >> 16
        return sample % operand + 1
