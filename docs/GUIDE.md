# Fernz detailed guide

A Z-machine interpreter library in Python, working toward a
Jericho-like API and optional Textual terminal player.

Fernz loads **raw V1-V8 story files** and completes the measured winning routes
for **all 17 retained V3 games**, including Zork I. See the [game inventory and
coverage](V3_GAMES.md) for exact builds, seeds, and limitations. It provides
header metadata, checksums, protected memory, instruction decoding, and V3
command input and immutable checkpoints. **V5 execution** completes winning routes for all 33 retained builds, with
per-game score, move, player and outcome profiles. 9:05, Balances and Sherlock
also have detours, loss paths and V5 Quetzal save/restore coverage. Linux compares public reference behavior; portable
vectors cover other platforms. See [V5 milestones](V5.md) for exact scope
and remaining features. **V8 execution** covers openings, commands and persistence
in all six retained games, plus complete winning routes and query APIs for
all six games; see [V8 compatibility](V8.md).
Full conformance and Blorb containers are still ahead.

**V4 execution** completes Trinity's 610-command winning walkthrough at seed 0,
with parser detours, a loss sequence, query APIs and save/restore coverage.
See [V4 compatibility](V4.md) for its input and screen conventions.

## Try it

Requires Python 3.11 or later and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --dev
uv run poe test-roms
uv run fernz --inspect games/zork1.z5
uv run fernz games/zork1.z5
```

The ROM tests download the retained Jericho game suite when `games/` is absent.
The inspection reports Z-machine **V3**, release **88**, serial **840726**, and
a valid checksum for this Zork I file, despite its `.z5` extension.
The CLI uses Textual when installed and falls back to the simple terminal player.
Install the optional frontend with `uv sync --extra textual`, then run
`uv run --extra textual fernz games/zork1.z5`.
Use `--rich` or `--simple` to select explicitly; use `--simple` for piped input.
Textual provides separate windows, styled output, scrollback, command history
and save dialogs. Ctrl+Q exits; the simple player exits at EOF.
See [the CLI guide](CLI.md) for controls and screen geometry.
Try `look`, `open mailbox`, `take leaflet`, `read leaflet`, and `inventory`.
The game's `save` and `restore` commands prompt for a filename. A blank filename
cancels, and overwriting an existing save requires confirmation.

```python
from fernz import Memory, Story

story = Story.from_file("games/zork1.z5")
print(story.header.version, story.header.serial)
print(story.verify_checksum())

memory = Memory(story)
value = memory.read_word(story.header.globals_table)
copy = memory.copy()
memory.reset()
```

`Story(data)` also accepts a byte buffer. `FernzEnv(path)` exposes the loaded
image as `env.story` and an independent memory instance as `env.memory`.
Its `reset()` runs supported V3/V4/V5/V8 startup and returns the complete opening transcript and
status information:

```python
from fernz import FernzEnv

env = FernzEnv("games/zork1.z5", seed=42)
try:
    observation, info = env.reset()
    print(observation.text, end="")
    print(info)  # {"score": 0, "moves": 0}
    for action in ("look", "open mailbox", "take leaflet", "read leaflet", "inventory"):
        observation, reward, done, info = env.step(action)
        print(observation.text, end="")
        if done:
            break
finally:
    env.close()
```

`reset()` and `step()` return an immutable `Observation` with a plain `.text`
transcript and an ordered `.stream` containing text and concise display tags.
Both windows contribute in execution order. The recognized Zork I command prompt
is omitted from `.text` and retained in `.stream`. Constructor options
`screen_width=80` and `screen_height=25` configure the display; the CLI accepts
`--screen-width` and `--screen-height`, measuring unspecified dimensions from
the available terminal game area. See [observations](OBSERVATIONS.md)
for the protocol, migration, and screen-state responsibilities.

`step()` returns only new output, a score delta, quit status, and status globals. Start with `reset()` or
restore a checkpoint with `set_state()`. Each reset and step has a default
budget of 1,000,000 instructions, adjustable with `max_steps=...`. Unsupported
opcodes fail with their name and address. Undo and full V3
execution support remain future work; `done` detects the `quit` opcode, not victory
or death that leaves the story running.

`env.initialized` reports whether an execution context exists, including after
quit. `env.awaiting_character` distinguishes single-key input from line input;
an empty action means Enter and a literal space means Space at a character
prompt. Both properties are safe before reset and after errors. See the
[host integration API](HOST_API.md) for error recovery and input conventions.

V3, V4, V5 and V8 `restart` are supported through the game's own RESTART command and confirmation.
It resets game memory, frames, and randomness while preserving Flags 2 and the
current output stream selection. With an explicit host seed, the restarted
episode repeats that seed's sequence; `seed=None` requests fresh entropy.
See [restart semantics](OVERVIEW.md#host-reset-and-v3-restart).

`get_state()` and `set_state()` support reusable in-memory checkpoints:

```python
env = FernzEnv("games/zork1.z5", seed=12)
env.reset()
state = env.get_state()
result = env.step("open mailbox")
env.set_state(state)
assert env.step("open mailbox") == result
print(len(state.ram))  # 11859 bytes of dynamic memory for this Zork I story.
branch = env.copy()
branch.step("take leaflet")  # The original environment stays at the mailbox.
print(branch.get_score(), branch.get_moves())
branch.close()
env.seed(42)  # Select a new seed for the next host reset.
env.reset()
env.close()
```

The immutable `GameState` includes memory, call frames, PC, pending input, output
selection, RNG state, and loss/victory response flags. V3, V4, V5 and V8 snapshots use
schema 5, including geometry, cursors, styles, colours, fonts, buffering,
nested memory-output state, and the active predictable or Python RNG state.
Checkpoints do not contain rendered screen cells.
It can also initialize another environment for the
same story. Restore validates the checkpoint before changing the live game and
returns `None`, with no execution or output. Fernz uses its own named fields;
Jericho tuples require conversion, and saved-game files use a separate format.
The test suite includes a [V3 state converter](STATE_INTEROP.md) for the
pinned Linux Jericho reference. It is not part of the installed package.

For persistent checkpoints, use `payload = state.to_bytes()` and
`GameState.from_bytes(payload, story=env.story)`, importing `GameState` from
`fernz`. The public codec validates the versioned payload before restoration.
`FernzEnv(env.story)` creates an independent environment without rereading the
ROM, with `game_path` set to `None`. See [checkpoint storage and restore
isolation](HOST_API.md#serializing-and-restoring-checkpoints).

`copy()` forks mutable execution state without running the game or rereading its
file. Copies share the immutable story and host callback references; external
storage destinations remain caller-owned. `seed(n)` returns the
selected value and applies it on the next `reset()`. Calling `seed()` or
`seed(None)` selects fresh entropy; zero remains deterministic. Checkpoints
retain their existing seed semantics, described in [RNG compatibility](RNG.md).
`get_score()` and `get_moves()` read the measured per-game globals (falling back
to V3 status globals for unprofiled score games), including
after quit. Unprofiled time-based games raise `NotImplementedError` for these
queries; their `info` exposes hours and minutes. Profiled time games use the
measured conventions listed in [V3 games](V3_GAMES.md).

`get_object(n)` and `get_world_objects()` return detached, locally mutable
`ZObject` snapshots with full names, containment links, attributes, and property
numbers. `get_player_object()` and `get_inventory()` use the recognized story's
player identity. `get_player_location()` now returns the same `ZObject` type,
including `.num` and `.name`. A known player profile uses its immediate container
(including vehicles); other V3 games use the status-line location convention.
See [object inspection](OBJECT_INSPECTION.md) for traversal examples, layout
requirements, and measured differences from Jericho. Cleaning remains deferred.
All 17 retained V3 builds and the pinned V5 9:05, Balances, and Sherlock builds support `game_over()`
and `victory()`. Outcome queries describe the latest response, including
recoverable deaths, and survive checkpoint restoration and copying. `done`
continues to indicate VM quit. Unknown builds raise `NotImplementedError` for
score limits and outcome queries. See [story queries](STORY_QUERIES.md) for
the measured behavior, supported story identity, and reference differences.

[LGOP coverage](LGOP.md) includes a complete win and Tiffany branches.
Its randomized scoring has no fixed maximum: `get_max_score()` raises
`NotImplementedError`, while its actual score, moves and player queries work.

V3, V4, V5 and V8 `save` and `restore` opcodes use Quetzal files. Library callers supply
`save_handler(data: bytes) -> bool` and `restore_handler() -> bytes | None`
when constructing `FernzEnv`; unavailable storage reports opcode failure.
Opcode restore keeps the current RNG, screen geometry, and Flags 2; V3 also
collapses the upper window as required by the specification. The existing `get_state()` / `set_state()` methods still restore their
complete deterministic checkpoints. See [save and restore](SAVE_RESTORE.md)
for a storage example and the separate contracts.

## Development

```sh
uv run poe check-all    # Offline tests, quality checks, and package validation
uv run poe test-fast    # PR selection: unit tests, all story files, short gameplay
uv run poe test-roms    # All 57 loading checks, plus Zork mailbox play and reset
uv run poe test-vectors # All 57 stories' metadata plus V3, V4, V5 and V8 gameplay archives
```

Short black-box Jericho comparisons run on every PR. The full Jericho and Frotz
suite runs through the manual **comprehensive** workflow. To run it locally on
Debian or Ubuntu:

```sh
sudo apt-get install --no-install-recommends frotz
uv sync --frozen --python 3.11 --group reference
uv run --no-sync poe test-full
```

A Python 3.12 matrix runs the offline suite and short recorded gameplay on macOS,
Windows x64, and Windows ARM. It reads `tests/vectors/<rom>_vectors.zip` for each
validated game and `storyfiles.zip` directly through `zipfile`, without Jericho or disk
extraction. The manual workflow keeps all live public-API comparisons and checks
every archive against fresh measurements, with complete vector replay on all
three platforms. Three balanced groups partition the additional V3 suites.
See [fast and comprehensive CI](CI.md) for timing budgets and manual runs,
[vectors](VECTORS.md), and
[testing philosophy](TESTING_PHILOSOPHY.md) for regeneration and content rules.

The comprehensive suite requires the Zork opening, mailbox, and full walkthrough comparisons,
including a second complete episode after reset. Tests obtain the walkthrough
and its seed through Jericho's documented `get_walkthrough()` and `seed()` calls
and generate reference observations at runtime. Every turn compares the
transcript, reward, quit status, score, and moves. A checkpoint comparison also
saves, advances, restores, and replays every command in both interpreters.
Six additional runs transfer state between interpreters after commands 35,
214, and 350, in both directions, then compare every remaining command through
the 350-point ending. The recipient does not replay the prefix.
A further walkthrough inserts actual save/restore opcodes at those three points,
changes score memory before each restore, and still matches every gameplay turn
through the ending. Quetzal tests exchange files with standalone Frotz in both
directions, using independent nested-call probes and Zork.

Off-path comparisons branch from 11 game checkpoints with 85 commands each,
including unknown verbs and nouns, futile actions, incomplete commands, and
container operations. Longer detours cover clarification, pronouns, vehicles,
recoverable death, and combat with five seeds. Each turn compares the response
and complete converted VM state; detours also replay from saved checkpoints.
Explicit boundary tests record question-mark and long-input differences without
filtering them from ordinary comparisons. See the [reference test details](OVERVIEW.md#black-box-reference-tests).

Fernz preserves the title and input newline that Jericho omits; tests assert
these separately. The Zork command prompt remains in `Observation.stream`,
while `Observation.text` omits it. At the final quit, Jericho adds one newline and reports
395 moves; Fernz reports the story's 394 moves, also printed by standalone Frotz.
The test asserts these exact final-turn differences. V3 output accepts legacy
tabs as three spaces, matching Jericho's plain transcript. Synthetic input probes
also compare accepted text and parse records with the standalone Frotz executable.

Predictable RNG sequences are compared against both interpreters using synthetic
V3/V4/V5/V8 stories, including cycle rollover and reseeding. Use a positive constructor
seed for shared reproducibility: Jericho treats host seed 0 as automatic, whereas
Fernz preserves a deterministic sequence for explicit zero, like Frotz. See
[RNG compatibility](RNG.md) for the contract and test setup, including
`FERNZ_DFROTZ` for a separately installed binary. Fernz executes V3, V4, V5 and V8; see [V8 compatibility](V8.md) for its staged coverage.

**Do not inspect Frotz or Jericho implementation source.** Implement from the
Z-machine specification and documented public APIs. Running Jericho through its
public API for functional comparison is allowed. These clean-room requirements
apply to every component, including random-number generation. Fernz's library
and simple CLI have no runtime dependencies; the `textual` extra is optional.

See [the overview](OVERVIEW.md) for the API contract, specification links,
CI coverage, fixture setup, and full clean-room requirements.
