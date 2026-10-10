# Fernz

A Z-machine interpreter library in Python, working toward a
Jericho-like API and a minimal interactive player.

Fernz loads **raw V1-V8 story files** and can **run Zork I (V3) to its first input
prompt**. It provides header metadata, checksums, protected memory, instruction
decoding, and a V3 execution foundation. Command input, full-game execution,
other execution versions, and Blorb containers are still ahead.

## Try it

Requires Python 3.11 or later and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --dev
uv run poe test-roms
uv run fernz --inspect games/jericho-game-suite/zork1.z5
uv run fernz games/jericho-game-suite/zork1.z5
```

The ROM tests download the retained Jericho game suite when `games/` is absent.
The inspection reports Z-machine **V3**, release **88**, serial **840726**, and
a valid checksum for this Zork I file, despite its `.z5` extension.

```python
from fernz import Memory, Story

story = Story.from_file("games/jericho-game-suite/zork1.z5")
print(story.header.version, story.header.serial)
print(story.verify_checksum())

memory = Memory(story)
value = memory.read_word(story.header.globals_table)
copy = memory.copy()
memory.reset()
```

`Story(data)` also accepts a byte buffer. `FernzEnv(path)` exposes the loaded
image as `env.story` and an independent memory instance as `env.memory`.
Its `reset()` runs V3 startup and returns the complete opening transcript and
status information:

```python
from fernz import FernzEnv

env = FernzEnv("games/jericho-game-suite/zork1.z5", seed=0)
try:
    observation, info = env.reset()
    print(observation, end="")
    print(info)  # {"score": 0, "moves": 0}
finally:
    env.close()
```

The CLI displays that transcript and exits; it does not accept commands yet.
`step()` still raises `NotImplementedError`. Startup has a default budget of
250,000 instructions, adjustable with `reset(max_steps=...)`. Unsupported
opcodes fail with their name and address. A successful Zork opening is not a
claim of complete V3 execution support.

## Development

```sh
uv run poe check-all    # Offline tests, quality checks, and package validation
uv run poe test-roms    # All 56 loading checks, plus Zork startup and reset
```

Black-box Jericho and Frotz comparisons run in Linux CI. To run them locally on
Debian or Ubuntu:

```sh
sudo apt-get install --no-install-recommends frotz
uv sync --frozen --python 3.11 --group reference
uv run --no-sync poe test-reference
```

The Zork opening comparison is required to pass, including after reset. Fernz
preserves the title and prompt that Jericho omits; the test asserts those pieces
separately and compares the remaining transcript exactly. The command sequence
remains an explicit expected failure until input is implemented.

Predictable RNG sequences are compared against both interpreters using synthetic
V3/V5/V8 stories, including cycle rollover and reseeding. Use a positive constructor
seed for shared reproducibility: Jericho treats host seed 0 as automatic, whereas
Fernz preserves a deterministic sequence for explicit zero, like Frotz. See
[RNG compatibility](docs/RNG.md) for the contract and test setup, including
`FERNZ_DFROTZ` for a separately installed binary. Fernz's execution support remains V3.

**Do not inspect Frotz or Jericho implementation source.** Implement from the
Z-machine specification and documented public APIs. Running Jericho through its
public API for functional comparison is allowed. These clean-room requirements
apply to every component, including random-number generation. Fernz has no runtime
dependencies.

See [the overview](docs/OVERVIEW.md) for the API contract, specification links,
CI coverage, fixture setup, and full clean-room requirements.
