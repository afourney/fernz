# Random modes and compatibility

Fernz's shared RNG implements the Z-machine `random` opcode independently of
story version. Its predictable sequences match the observed behavior of
**Jericho 3.3.1 and the Frotz 2.54/2.55 `dfrotz` executables**. This is a
compatibility choice: [Standard §2.4](https://inform-fiction.org/zmachine/standards/z1point1/sect02.html)
requires repeatability but does not prescribe a universal generator. Ordinary
random mode uses a separate per-environment Python `random.Random` instance
and `randrange(1, n + 1)` for unbiased bounded sampling.

Development follows the [mandatory clean-room requirements](OVERVIEW.md#mandatory-clean-room-requirement).
Use the specification and black-box comparisons through public interfaces.

## Opcode behavior

The operand is a signed 16-bit word. Positive operands produce a result from
1 through the operand, inclusive; every draw advances the active generator, even when
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

The compatibility state has 31 bits, and each sample uses its upper 15 bits.
Its remainder mapping introduces modulo bias for ranges that do not divide
32768. This mapping is retained only for predictable compatibility trajectories;
ordinary random mode uses Python's rejection-based bounded sampling instead.

For example, opcode seed 1000 and range 6 produce
`2, 5, 6, 6, 1, 1, 5, 5, 6, 3, ...` in all three tested references.

## Host seeding and reset

`FernzEnv(path, seed=N)` accepts an integer from 0 through `2**31-1`. An explicit
host seed initializes the affine generator, including small seeds. It does not
select the counting mode. For example, constructor seed 5 and opcode `random
-5` intentionally produce different sequences.

With an explicit host seed, `env.reset()`, `random 0`, and `restart` restore
that host-seeded sequence, discarding any counting cycle or opcode seed. With
`seed=None`, each creates a Python generator seeded with
`secrets.randbits(256)`. Random draws do not request fresh system entropy.
Unseeded trajectories are not part of the cross-interpreter compatibility
contract. A negative `random` operand discards the Python generator and enters
the appropriate predictable mode, even when the host seed is `None`. The next
`random 0` or restart reapplies the host policy.

`env.seed(value)` selects and returns the host seed for the next `env.reset()`.
It validates without executing, drawing randomness, or obtaining entropy. The
active RNG and its host reseeding policy remain unchanged, including for
`random 0` and V3 `restart`. Calling `seed()` or `seed(None)` selects automatic
seeding and returns `None`. Fernz keeps its existing policy here; it does not
select a game's walkthrough seed automatically as Jericho may do.

`copy()` preserves the active RNG state, active host seed, and pending reset
seed independently. This has one measured difference from Jericho 3.3.1: after
`seed(new_seed)` followed by `copy()` before reset, the Jericho copy uses the
new seed at its next `random 0` or restart. Fernz's copy retains the source's
active host policy until host reset. Both use the new seed after `reset()`.
The reference suite asserts these exact sequences through public calls.

**Zero selects different host policies.** Frotz's `-s 0` and Fernz's explicit
`seed=0` select a reproducible zero sequence. Jericho 3.3.1's public `seed(0)`
selects the supported game's recommended default: 12 for our Zork I build,
10 for Cutthroats, 4 for HHGG, and zero for the other retained V3 games. Those
zero-default games produce reproducible trajectories. For an unsupported
synthetic story, Jericho returns -1 and selects automatic seeding. The earlier
observation on an unsupported probe did not generalize to supported games.
Use the measured per-game seed explicitly in reference comparisons.

The constructor's explicit zero remains reproducible. RNG instances belong to
individual machines and do not share process-global state. Undo remains future
work.

Host-side `get_state()` / `set_state()` checkpoints capture the active generator
and the host seed policy. Restoring neither draws a value nor requests entropy;
it resumes the saved sequence. The restored host seed also governs later
`reset()`, `random 0`, and `restart` calls. If that seed is `None`, those later
operations still request fresh entropy. This host API supports deterministic
exploration; it has a different contract from the standard's story-level
save/restore opcodes.

Schema-5 checkpoints include an optional immutable `rng.python_state` from
Python's `getstate()`. Its presence identifies ordinary random mode; the compact
`state`, `period`, and `position` fields are then zero and `host_seed` is `None`.
Predictable mode keeps those compact fields and has `python_state=None`, with
no Python generator allocated. Only ordinary-mode checkpoints carry the larger
state (624 32-bit words plus an index and Python's state-format metadata).
Copying or restoring uses `setstate()` without requesting entropy or advancing
either generator. Malformed state is rejected before changing the environment.

Only the current checkpoint schema is accepted. Fernz is unreleased and provides
no migration or compatibility paths for earlier Fernz formats. Exact Python
bounded sequences are not promised across arbitrary future Python releases.

Existing game-vector archives use explicit seeds. Their compact RNG expectations
and version-2 reference fingerprints remain unchanged; no Python RNG dumps
are added to the ZIP files. Synthetic tests cover ordinary-mode sampling,
switching, checkpoint replay, independent copies, and invalid state.

The pending next-reset seed is outside the captured `GameState`.
`set_state()` uses the captured active host seed for subsequent resets as well,
replacing any pending selection made through `seed()`.

V3/V5 `save` writes no RNG state into its Quetzal file. `restore` retains the
receiving machine's current RNG state and host seed, without drawing or reseeding
during restoration. Any subsequent story instructions can of course draw from
that sequence. A file loaded into a fresh process therefore does not promise the
donor's future random outcomes. See [save and restore](SAVE_RESTORE.md).

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
  independence, controlled entropy, checkpoint restoration in both modes, and
  V3 opcode/environment integration.
- Required reference tests compare the shared RNG against both interpreters using
  V3/V5/V8 probes. V3 also runs through Fernz's complete execution path. These
  tests do not establish V8 execution support; Fernz executes V3 and V5.
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
