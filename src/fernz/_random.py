"""Version-independent random opcode behavior, verified against black-box references."""

import secrets
from operator import index


class RandomGenerator:
    """Generate the predictable sequences observed in Jericho and Frotz.

    Opcode seeds 1-999 select a counting cycle; larger seeds select an affine
    generator. An explicit host seed always selects the affine generator,
    including zero. None requests system entropy. See docs/RNG.md for the
    compatibility boundary, observations, and mathematical parameter check.
    """

    def __init__(self, seed: int | None = None) -> None:
        """Choose a host seed in 0..2**31-1, or request automatic seeding."""
        if seed is not None:
            seed = index(seed)
            if not 0 <= seed < 2**31:
                raise ValueError("Host seed must be in 0..2**31-1, or None")
        self._host_seed = seed
        self.reset()

    def reset(self) -> None:
        """Start the host-seeded sequence again, leaving any counting cycle."""
        self._state = self._host_seed if self._host_seed is not None else secrets.randbits(31)
        self._period = 0
        self._position = 0

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
            self._period = seed if seed < 1000 else 0
            self._position = 0
            self._state = seed
            return 0

        if self._period:
            sample = self._position
            self._position = (self._position + 1) % self._period
        else:
            # Recovered from printed outputs of independently assembled probes.
            # Only the low 31 state bits affect the observed 15-bit samples.
            self._state = (22695477 * self._state + 1) % (2**31)
            sample = self._state >> 16
        return sample % operand + 1
