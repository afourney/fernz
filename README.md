# Fernz

A clean-room Z-machine interpreter library in Python, working toward a
Jericho-like API and a minimal interactive player.

Fernz currently loads **raw V1-V8 story files**, exposes header metadata, checks
checksums, and provides protected memory. Story execution is the next stage;
Zork I is the first gameplay target. Blorb containers are not supported yet.

## Try it

Requires Python 3.11 or later and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --dev
uv run poe test-roms
uv run fernz --inspect games/jericho-game-suite/zork1.z5
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
Its `reset()` and `step()` methods still raise `NotImplementedError`.

## Development

```sh
uv run poe check-all    # Offline tests, quality checks, and package validation
uv run poe test-roms    # Loading and memory checks for all 56 retained games
```

Black-box Jericho comparisons run in Linux CI. To run them locally on Linux:

```sh
uv sync --frozen --python 3.11 --group reference
uv run --no-sync poe test-reference
```

**Do not inspect Frotz or Jericho implementation source.** Implement from the
Z-machine specification and documented public APIs. Running Jericho through its
public API for functional comparison is allowed. Fernz has no runtime dependencies.

See [the overview](docs/OVERVIEW.md) for the API contract, specification links,
CI coverage, fixture setup, and full clean-room requirements.
