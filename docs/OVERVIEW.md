# Fernz overview

Fernz is intended to become a Z-machine interpreter for common Z-machine story
formats. The first implementation milestone provides story loading and memory;
execution remains future work.

## Mandatory clean-room requirement

**Fernz must be a clean-room reimplementation. Do NOT read or inspect Frotz or
Jericho source code.** This requirement applies to all implementation, debugging,
and testing work on Fernz.

- **Implement independently from the specifications.** Use the Z-machine
  standard and its annotated companion for interpreter behavior, and Jericho's
  public API documentation for API compatibility.
- **Do not copy, port, translate, or derive Fernz code or design from Frotz or
  Jericho source code.** This includes source found in their repositories,
  installed packages, or vendored copies.
- **Black-box functional comparison is allowed.** Frotz or Jericho may be run
  through their public interfaces to compare inputs, outputs, and observable
  behavior, and to support functional tests. Permission to run them does not
  permit inspecting their implementation.
- **Jericho is a development-only reference dependency.** Installing or building
  it through the package manager is allowed for these tests. Never browse the
  installed source, use source inspection, or access its private/native internals
  to guide Fernz. Fernz itself must not import or depend on Jericho at runtime.

The Jericho repository link below identifies the upstream project only. It is
**not permission to browse its source or use it as an implementation reference**.
This requirement supersedes the earlier proposal to use Jericho's source as a
reference.

## Project goals

- Provide an installable Python package that can be used as a library.
- Mirror Jericho's Python API, or get as close as practical. The exact compatibility
  scope has not yet been decided.
- Implement the interpreter in pure Python as much as possible.
- Potentially provide a minimal interactive CLI for manual testing and playing
  through test games.

The Z-machine specifications will guide interpreter behavior. Jericho's public
API documentation will guide API compatibility, subject to the clean-room
requirement above.

## References

- [Z-machine Standard 1.1](https://inform-fiction.org/zmachine/standards/z1point1/index.html)
  — the primary specification reference.
- [Annotated Z-machine specification](https://zspec.jaredreisinger.com/)
  — a companion reference for explanations and implementation notes.
- [Jericho quickstart documentation](https://jericho-py.readthedocs.io/en/latest/tutorial_quick.html)
  — examples of the library API and its use.
- [Jericho public environment API](https://jericho-py.readthedocs.io/en/latest/frotz_env.html)
  — the public calls used for black-box comparisons.
- [Jericho upstream project](https://github.com/microsoft/jericho)
  — project identification only; **do not inspect its source code**. Running
  Jericho for black-box functional testing and comparison is allowed.
- [BYU-PCCL Z-machine game collections](https://github.com/BYU-PCCL/z-machine-games)
  — the source of the test games.
- [Game collection ZIP download](https://github.com/BYU-PCCL/z-machine-games/archive/master.zip)
  — the archive used during setup.

## Environment setup so far

1. Started with the existing `fernz` repository and Python package scaffold.
   `pyproject.toml` declares Python 3.11 or later, uses the `uv_build` build backend,
   and currently declares no runtime dependencies. Package source is under
   `src/fernz/`.
2. Confirmed that a local `.venv/` already exists and uses CPython 3.12.14. This
   environment was present before the game collection setup; it was not created
   as part of these steps.
3. Downloaded the BYU-PCCL archive linked above, verified its ZIP integrity, and
   extracted its contents into `games/`. The nested large game collection was
   also unpacked initially.
4. Kept only `games/jericho-game-suite/`. Removed the Autoplay suite, the large
   game collection, the downloaded archives, and the collection-level README.
5. Removed **Leather Goddesses of Phobos** (`lgop.z3`) from the Jericho suite.
   The retained suite now contains **56 game files**. Verified that those files
   were unchanged during cleanup.
6. Created `docs/OVERVIEW.md` to record the project direction, references, and
   setup history.

All 56 retained games are used for loading, checksum, and memory tests. They have
not yet been executed with Fernz. Version detection uses the header: for example,
`zork1.z5` contains a V3 story, release 88, serial `840726`.

## Test fixture setup

Install the development dependencies with `uv sync --dev`, then run tests with
`uv run pytest`. Tests that need ROMs can request the session-scoped
`jericho_games` pytest fixture, which returns the path to
`games/jericho-game-suite/`.

When the repository's `games/` directory is absent, the fixture downloads the
BYU-PCCL ZIP linked above and extracts only the Jericho suite, excluding
`lgop.z3`. Extraction is staged before creating `games/`, so a failed download
or extraction can be retried. The ZIP and other collections are not retained.

An existing `games/` directory is left untouched and does not trigger a download.
If it lacks `jericho-game-suite/`, the fixture reports an error. Tests that do not
request the fixture do not download games. Downloaded ROMs are ignored by Git.
The download currently follows upstream `master`; it is not yet pinned to an
immutable revision. This download mechanism does not establish redistribution
rights for the games.

## Development tasks and continuous integration

The development workflow adapts the Poe tasks and CI structure from
[cabin-fever-x86](https://github.com/afourney/cabin-fever-x86/blob/main/pyproject.toml)
and the package validation from
[jlv](https://github.com/afourney/jlv/blob/main/.github/workflows/release.yml).
Run `uv sync --dev` to install the locked development tools, then use:

| Command | Purpose |
| --- | --- |
| `uv run poe check` | Check formatting, lint, and spelling. |
| `uv run poe fix-all` | Apply formatting and automatic lint fixes. |
| `uv run poe test` | Run synthetic and API tests without Jericho or ROM downloads. |
| `uv run poe test-roms` | Load all 56 retained ROMs and check their checksums and memory. |
| `uv run --no-sync poe test-reference` | Run the opt-in Jericho reference tests after installing the reference group below. |
| `uv run poe build-check` | Build the wheel and source distribution, validate their contents, and smoke-test an isolated wheel installation. |
| `uv run poe check-all` | Run code checks, synthetic/API tests, and build validation; ROM and reference tests run separately. |

Individual tasks include `format`, `format-fix`, `lint`, `lint-fix`, `spell`,
`build`, and `check-dist`. Build validation expects one wheel and one source
distribution in `dist/`; remove stale distributions after changing versions.
Formatting and lint cover `src/`, `tests/`, and `scripts/`. Spelling checks also
cover documentation and CI configuration, but exclude test inputs and ROMs.

`.github/workflows/ci.yml` runs on pull requests, pushes to `main`, and manual
dispatch. Separate jobs check code quality and lockfile consistency, run pytest
on Python 3.11 through 3.14, and validate the built package. CI uses the same Poe
tasks as local development, with frozen dependency installation. Superseded runs
are cancelled and workflow permissions are limited to reading repository contents.
A separate Linux/Python 3.11 job installs the optional reference group and runs
the ROM loading tests followed by the Jericho comparisons. Both use the same
`jericho_games` fixture. Missing dependencies, download failures, and reference
execution failures fail that job; it does not silently skip them.

The package check verifies metadata, package files, the `py.typed` marker, and
that neither distribution contains game ROMs. It then installs the wheel into a
temporary virtual environment and imports Fernz independently of the checkout.
There is no publishing workflow.

Tests may download the Jericho corpus through `jericho_games` when needed. CI
does not cache or upload ROMs. Synthetic tests cover all eight story versions.
Real-ROM tests have a separate case for each retained game, covering V3 (16),
V4 (1), V5 (33), and V8 (6), plus a Zork I metadata check through `FernzEnv`.
V1, V2, V6, and V7 currently have synthetic coverage only. Execution conformance
tests will be added with the interpreter.

## Black-box reference tests

Jericho 3.3.1 is pinned in the optional `reference` development dependency group
and locked with its dependencies in `uv.lock`. That group uses Python 3.11 on
Linux, keeping Jericho's native build and dependencies out of the normal Python
test matrix and Fernz's runtime dependencies. Install it and run the tests with:

```sh
uv sync --frozen --python 3.11 --group reference
uv run --no-sync poe test-reference
```

The installation requires C build tools such as `gcc` and `make`, already present
on the Ubuntu CI runners. These tests need no additional spaCy language model.
Normal pytest runs deselect the `reference` and `rom` markers, so they neither
import Jericho nor download games. To select comparisons directly, use
`uv run --no-sync pytest -m reference -ra --tb=short`.

`tests/test_reference.py` uses only the documented `FrotzEnv` constructor,
`reset()`, `step()`, and `close()` calls. It verifies the SHA-256 of our Zork I
fixture (`zork1.z5`, whose header is V3), runs Jericho with seed 0, and records an
opening followed by `look`, `open mailbox`, `take leaflet`, `read leaflet`, and
`inventory`. A second episode verifies repeatability after reset. Reference
observations are generated during the test, rather than committed as game text.

Two explicit Fernz comparisons check the opening and the short sequence,
including reset after play. They compare observation text, reward, completion,
score, and move count. Text normalization is limited to CRLF versus LF; score
and moves are compared individually to allow additional metadata keys.

**These are targets, not passing interpreter coverage yet.** Both comparisons
currently have strict expected-failure markers limited to `NotImplementedError`,
because Fernz cannot execute stories. Assertion mismatches still fail. An
unexpected pass also fails until its marker is removed, making progress an
explicit change. A separate, unmarked Jericho smoke test must always pass, so a
broken reference cannot be hidden by the expected failures.

The sequence avoids random encounters. Equal numeric seeds alone do not guarantee
equal random streams across interpreters. Expand comparisons as Fernz gains
execution, state restoration, and other public APIs. The Z-machine standard
remains authoritative when it and a reference interpreter disagree; investigate
the discrepancy instead of copying reference behavior automatically. Loading and
memory tests for all V1-V8 use independent specification-based fixtures,
since these public Jericho calls execute the game as part of initialization.

## Current scope

Work includes version-aware loading and protected memory for raw V1-V8 stories,
an inspection CLI, test-data fixtures, CI checks, and black-box reference targets.
No interpreter execution is implemented. Zork I (V3) remains the first playable
execution target. Blorb extraction, text decoding, instruction execution, and
save-game formats are outside this milestone.

## Story loading and memory

```python
from fernz import Memory, Story

story = Story.from_file("games/jericho-game-suite/zork1.z5")
assert story.header.version == 3
assert story.verify_checksum() is True
memory = Memory(story)
initial_global = memory.read_word(story.header.globals_table)
```

`Story(data)` accepts bytes, a bytearray, or a memoryview and retains immutable
bytes. `Story.from_file(path)` reads a regular file and preserves normal I/O
exceptions. Malformed or unsupported raw images raise `StoryFormatError`, a
`ValueError` subclass. Both the story and its initial `StoryHeader` are immutable.
This header is a snapshot, not a live view of changing memory.

The loader validates header length, version, declared size, entry address, memory
bounds, and the extents of globals, object defaults, abbreviations, alphabets,
and header extensions when present. It does not validate every table entry or
instruction. Addresses and offsets exposed by the header are byte addresses;
`initial_value` retains the raw startup word. `entry_address` resolves V6's main
routine address; `entry_is_routine` distinguishes it from the initial instruction
address used by the other versions. Routine and string unpacking use the
version-specific rules, including separate offsets in V6/V7.

`story.data` retains the full file, including padding. `story.size` and memory
length exclude padding when a length is declared. `verify_checksum()` returns
True or False using the original image, or None for V1/V2 and early V3 files
without length/checksum fields. A mismatch does not prevent inspection or
loading. V4-V8 require a nonzero declared length. A stored zero checksum with a
known length is verified normally. Later header fields are ignored in earlier
versions; a missing extension word reads as zero.

Historic high-memory markers are retained as metadata, without imposing an
ordering between that marker, the entry point, and static memory. This permits
the retained Trinity, Sherlock, Seastalker, and Plundered Hearts images to load.
The static-memory base remains the enforced write boundary.

`Memory(story)` creates an independent instance. Its `read_byte`, `read_word`,
and `read_bytes` methods check bounds; words are unsigned, big-endian, and need
not be aligned. Reads cover the whole logical image for future instruction and
string access; opcode-specific addressing limits belong to the future CPU.
Corresponding write methods reject out-of-range values, writes outside dynamic
memory, and changes to protected header bits or extension words. Only the
game-writable Flags 2 bits are allowed in the header. Invalid multi-byte writes
leave all bytes unchanged. Errors raise `MemoryAccessError` (a `ValueError`).

`memory.copy()` copies current contents independently. `memory.reset()` restores
the original image exactly. This low-level reset is not VM restart or save
restoration: managing CPU/stack state and preserving interpreter flags belongs
to the later execution layer. No writable memory views are exposed.

Implementation references are Standard 1.1
[memory and addressing](https://inform-fiction.org/zmachine/standards/z1point1/sect01.html),
[headers](https://inform-fiction.org/zmachine/standards/z1point1/sect11.html),
[text tables](https://inform-fiction.org/zmachine/standards/z1point1/sect03.html),
[globals](https://inform-fiction.org/zmachine/standards/z1point1/sect06.html),
[object defaults](https://inform-fiction.org/zmachine/standards/z1point1/sect12.html),
[verify](https://inform-fiction.org/zmachine/standards/z1point1/sect15.html#verify),
and [conventional metadata](https://inform-fiction.org/zmachine/standards/z1point1/appb.html).

## CLI and environment API

After `uv sync --dev`, run `uv run fernz --help` or
`uv run python -m fernz --help`. The installed `fernz` command targets
`fernz._cli:main` inside `src/fernz/`. Modules prefixed with `_` are private;
import `Story`, `StoryHeader`, `Memory`, `StoryFormatError`, `MemoryAccessError`,
and `FernzEnv` from `fernz` for the public library
interface and `fernz` or `python -m fernz` for the public CLI.
`fernz --inspect GAME` prints JSON metadata and exits with 0. It reports both
physical file size and logical story size, plus checksum validity (null when
unavailable). A checksum mismatch is reported as false without rejecting the
inspection. Help exits with 0; missing/invalid arguments, paths, or story formats
exit with 2. `fernz GAME` loads the story, then reports unimplemented execution
on stderr and exits with 1. There is no interactive prompt or VM execution yet.
The CLI delegates to the public library.

The deliberately small public contract is:

| Interface | Contract |
| --- | --- |
| `from fernz import FernzEnv` | Public environment class; no Jericho runtime dependency. |
| `FernzEnv(game_path)` | Accepts a string or text path-like object, stores a `Path` in `game_path`, and loads a raw V1-V8 story. Missing/inaccessible paths raise `OSError` subclasses; non-regular paths raise `ValueError`; invalid story data raises `StoryFormatError`. |
| `env.story`, `env.memory` | Immutable story image and independent protected memory instance. |
| `env.reset()` | Planned result: `(observation: str, info: dict[str, object])`. Currently raises `NotImplementedError`. |
| `env.step(action: str)` | Planned result: `(observation: str, reward: int, done: bool, info: dict[str, object])`. Currently raises `NotImplementedError`. |
| `env.close()` | Idempotent resource cleanup; currently a no-op because no resources are held. |

The tuple shapes follow the permitted
[Jericho public quickstart](https://jericho-py.readthedocs.io/en/latest/tutorial_quick.html).
Future metadata may include score and move count; the scaffold returns no
invented observations, rewards, or metadata. This is an interface outline, not a
claim of drop-in Jericho compatibility. The original `hello()` helper remains
available for compatibility with the initial package scaffold.

Caller-side context was limited to the root
[`play_jericho.py` in cabin-fever-x86](https://github.com/afourney/cabin-fever-x86/blob/b4933c8b167635c9ffbd7cd8ffd1307fc0b3d52e/play_jericho.py).
That consumer uses construction, reset, text steps, and cleanup. Its additional
save restoration, location lookup, score/move queries, and game-over/victory
queries are deferred. Its direct `frotz_lib` access is outside this public
contract; binary saves and interpreter internals are not supported. No Frotz or
Jericho implementation source was inspected or copied.

API tests use temporary synthetic files without requesting the game fixture
or downloading ROMs. Package validation also exercises the installed command and
module entry point from a temporary directory outside the checkout.
