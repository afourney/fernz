# Random-number compatibility

Fernz's shared RNG implements the Z-machine `random` opcode independently of
story version. Its predictable sequences match the observed behavior of
**Jericho 3.3.1 and the Frotz 2.54/2.55 `dfrotz` executables**. This is a
compatibility choice: [Standard §2.4](https://inform-fiction.org/zmachine/standards/z1point1/sect02.html)
requires repeatability but does not prescribe a universal generator.

Development follows the [mandatory clean-room requirements](OVERVIEW.md#mandatory-clean-room-requirement).
Use the specification and black-box comparisons through public interfaces.

## Opcode behavior

The operand is a signed 16-bit word. Positive operands produce a result from
1 through the operand, inclusive; every draw advances the sequence, even when
the requested range is 1. Zero and negative operands return zero.

| Operation | Behavior |
| --- | --- |
| `random -1` through `random -999` | Start a counting cycle with that seed's magnitude as its period. |
| `random -1000` through `random -32768` | Initialize the affine generator with that seed's magnitude. |
| `random 0` | Leave predictable opcode mode and reseed using the host policy described below. |

In counting mode, the raw samples are `0, 1, ..., seed-1`, repeating. The result
is `sample % range + 1`; changing ranges does not restart the cycle. Thus seed
5 and range 3 give `1, 2, 3, 1, 2, 1, 2, 3, ...`.

Fernz uses the following affine recurrence for large seeds:

```text
state  = (22695477 * state + 1) modulo 2**31
sample = state >> 16
result = sample modulo range + 1
```

The state has 31 bits, and each sample uses its upper 15 bits. The final
remainder mapping introduces modulo bias for ranges that do not divide 32768.

For example, opcode seed 1000 and range 6 produce
`2, 5, 6, 6, 1, 1, 5, 5, 6, 3, ...` in all three tested references.

## Host seeding and reset

`FernzEnv(path, seed=N)` accepts an integer from 0 through `2**31-1`. An explicit
host seed initializes the affine generator, including small seeds. It does not
select the counting mode. For example, constructor seed 5 and opcode `random
-5` intentionally produce different sequences.

With an explicit host seed, both `env.reset()` and the opcode `random 0` restore
that host-seeded sequence, discarding any counting cycle or opcode seed. With
`seed=None`, both obtain fresh system entropy. Unseeded operation uses the same
affine generator, seeded with `secrets.randbits(31)`. Unseeded trajectories are
not part of the cross-interpreter compatibility contract.

**Explicit host seed 0 differs between the references.** Frotz's `-s 0` gives a
fixed sequence, whereas Jericho's constructor `seed=0` was observed to use
automatic seeding. Fernz retains deterministic behavior for an explicit zero,
matching Frotz. Use a positive host seed for comparisons involving all three
interpreters, or a negative opcode operand to enter predictable mode in the
story. This distinction does not affect the existing Zork opening comparison,
which does not rely on random encounters.

This replaces Fernz's initial Python `random.Random` implementation, so seeded
sequences change from that first execution milestone. The constructor's explicit
zero remains reproducible. RNG instances belong to individual machines and do
not share process-global state. Save, undo, and VM restart remain future work.

## Compatibility evidence

The compatibility rules were checked through executable behavior using
independently assembled synthetic stories.

Each probe executes a list of `random` instructions, prints each result with
`print_num`, and quits. It uses no compiler, commercial ROM, or game-specific
Jericho hooks. The same instruction bytes are packaged in V3, V5, and V8 images.
Jericho runs through the documented constructor, `reset`, and `close`; Frotz runs
as a subprocess using its public CLI. No native-library internals are accessed.

The reference tests compare two draws for each of 135 seeds, plus longer
sequences with changing ranges, cycle rollover, repeated seeding, and host-seed
restoration.

## Tests and dependencies

- Normal tests include fixed observed vectors, signed-word boundaries, per-machine
  independence, controlled entropy, and V3 opcode/environment integration.
- Required reference tests compare the shared RNG against both interpreters using
  V3/V5/V8 probes. V3 also runs through Fernz's complete execution path. These
  tests do not claim that Fernz can execute V5/V8 stories yet.
- The reference job installs the distribution's binary `frotz` package and prints
  its version. Jericho is pinned to 3.3.1; the distribution package version may
  change with the runner image, and any sequence mismatch fails the job.

On Debian or Ubuntu, install `frotz` alongside the Python reference dependencies:

```sh
sudo apt-get install --no-install-recommends frotz
uv sync --frozen --python 3.11 --group reference
uv run --no-sync poe test-reference
```

For a separately installed binary, set `FERNZ_DFROTZ` to its executable path.
Tests otherwise look for `dfrotz` on PATH and then `/usr/games/dfrotz`. A missing
binary fails reference testing rather than skipping compatibility checks.

Frotz reports GPL-2.0-or-later licensing. It is an external development/test
executable, not distributed with Fernz or imported at runtime. Probe stories
are generated from this repository's own test code; no external test vectors
or interpreter implementation code are vendored.
