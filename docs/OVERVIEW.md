# Fernz overview

Fernz is a Z-machine interpreter for common Z-machine story formats. It loads
V1-V8 stories and completes the measured winning routes for all 17 retained V3 games, including Zork I's 396-command route at seed 12.
See [V3 gameplay coverage](V3_GAMES.md) for exact builds and limitations. The library and a
minimal interactive CLI support V3, V4, V5 and V8 execution. All 33 retained V5
builds complete measured winning routes; see [V5](V5.md). V8 covers all six
retained openings and action/persistence scenarios, with full winning routes
and query APIs for all six games; see [V8](V8.md).

## Mandatory clean-room requirement

**Fernz must be a clean-room reimplementation. Do NOT read or inspect Frotz or
Jericho source code.** This requirement applies to all implementation, debugging,
and testing work on Fernz, including random-number generation. Use specifications,
documented public APIs, and black-box observations to guide development.

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

## Project goals

- Provide an installable Python package that can be used as a library.
- Mirror Jericho's Python API, or get as close as practical. Include the
  [Cabin Fever consumer requirements](CABIN_FEVER_COMPATIBILITY.md) as a concrete
  compatibility target alongside the broader public API.
- Implement the interpreter in pure Python as much as possible.
- Potentially provide a minimal interactive CLI for manual testing and playing
  through test games.

The Z-machine specifications will guide interpreter behavior. Jericho's public
API documentation will guide API compatibility, subject to the clean-room
requirement above.

Fernz is pre-1.0 (0.0.x releases). Accept only the current Fernz checkpoint and data
formats; do not add compatibility shims or migrations for earlier Fernz formats
unless explicitly requested. Update tests and test adapters with format changes.

The [world-state hash and action discovery investigation](WORLD_STATE_HASH.md)
records public-reference measurements and unresolved questions. Both APIs remain
unimplemented; this work is paused pending further user direction.

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

## Project layout and game collection

`pyproject.toml` declares Python 3.11 or later, uses the `uv_build` build backend,
and declares no required runtime dependencies (Textual is an optional extra).
Package source is under `src/fernz/`.

The test games come from the `jericho-game-suite` directory of the BYU-PCCL
archive linked above, extracted directly into `games/`: **57 game files**,
including the measured Leather Goddesses of Phobos build (`lgop.z3`). The other
collections in that archive are not used.

All 57 retained games are used for loading, checksum, and memory tests. Zork I
also has startup, mailbox play, quit, reset, and a full walkthrough comparison.
Version detection uses the header: for example, `zork1.z5` contains a V3 story,
release 88, serial `840726`.

## Test fixture setup

Install the development dependencies with `uv sync --dev`, then run tests with
`uv run pytest`. Tests that need ROMs can request the session-scoped
`jericho_games` pytest fixture, which returns the path to `games/`.

When the repository's `games/` directory is absent, the fixture downloads the
BYU-PCCL ZIP linked above and extracts the complete Jericho suite, including
`lgop.z3`, directly into `games/`. Extraction is staged before creating `games/`,
so a failed download or extraction can be retried. The ZIP and other collections
are not retained.

An existing `games/` directory is left untouched and does not trigger a download.
If it predates LGOP inclusion, move it aside and rerun the fixture to download
the complete suite, or add the pinned `lgop.z3` manually.
If it lacks `zork1.z5` directly inside `games/`, the fixture reports an error.
For older downloads, move the contents of `games/jericho-game-suite/` into `games/`.
Tests that do not request the fixture do not download games. Downloaded ROMs are
ignored by Git.
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
| `uv run poe check` | Check formatting, lint, spelling, and strict package types. |
| `uv run poe typecheck` | Run Pyright over the entire shipped package and public typing examples. |
| `uv run poe fix-all` | Apply formatting and automatic lint fixes. |
| `uv run poe test` | Run synthetic and API tests without Jericho or ROM downloads. |
| `uv run poe test-fast` | Run the fast PR selection: offline tests, all story files, and short portable gameplay. |
| `uv run --no-sync poe test-fast-reference` | Run bounded live Jericho comparisons on Linux. |
| `uv run --no-sync poe test-full` | Run all tests and archive freshness checks in the Linux reference environment. |
| `uv run poe test-roms` | Load all 57 retained ROMs, check checksums and memory, and run Zork I startup, mailbox play, quit, and reset. |
| `uv run --no-sync poe test-reference` | Compare all 16 seeded V3 walkthroughs, detours, and synthetic probes with the references, after installing the reference group below. |
| `uv run poe test-vectors` | Check all 57 stories' metadata and replay all 17 V3 archives on any supported platform without Jericho. |
| `uv run --no-sync poe generate-vectors` | Explicitly regenerate all 17 ZIPs using the pinned Linux reference environment. |
| `uv run --no-sync poe check-vectors` | Check all 17 ZIPs against fresh reference/specification measurements without rewriting them. |
| `uv run poe build-check` | Build the wheel and source distribution, validate their contents, and smoke-test an isolated wheel installation. |
| `uv run poe check-all` | Run code checks, synthetic/API tests, and build validation; ROM and reference tests run separately. |

Individual tasks include `format`, `format-fix`, `lint`, `lint-fix`, `spell`,
`build`, and `check-dist`. Build validation expects one wheel and one source
distribution in `dist/`; remove stale distributions after changing versions.
Formatting and lint cover `src/`, `tests/`, and `scripts/`. Spelling checks also
cover documentation and CI configuration, but exclude test inputs and ROMs.

`.github/workflows/fast.yml` runs on pull requests, pushes to `main`, and manual
dispatch, under the name **check**. It keeps code quality, lockfile consistency,
all offline tests on Linux/Python 3.11–3.14, and package validation. Linux also
runs all story loading checks, short vector replay, and bounded live Jericho
comparisons. Python 3.12 portable jobs run offline tests, all 57 story files,
and short gameplay on macOS, Windows Server 2025 x64, and Windows 11 ARM,
without Jericho. Every V3 game gets its opening and five route commands, with
copy, snapshot restore, and reset checks. Every archive's member hashes are
verified. Test steps have two-minute limits and jobs have five-minute limits;
the target is under three minutes of runner execution.

`.github/workflows/ci.yml`, named **comprehensive**, retains the complete matrix
and runs only by manual dispatch. Its core Linux job includes complete Zork I
comparisons and checks the Zork I and story-file archives against fresh
measurements. Three additional Linux jobs each run five V3 games against the
public reference and verify their archives. The portable matrix has core and
V3 groups on all three platforms. The 17 archives hold hashes and metadata
for all 57 story files and all 17 V3 games' routes, detours, losses, seeds, and
save/restart/restore. No archive contains ROMs, narrative, or memory dumps.

Both workflows use the same Poe tasks as local development, frozen dependency
installation, read-only repository permissions, and cancellation of superseded
runs. Missing dependencies, fixture downloads, or reference execution fail the
selected checks; they do not silently skip them. See [CI](CI.md) for manual
validation of a PR's current commit and the fast-suite timing policy.
See [our testing philosophy](TESTING_PHILOSOPHY.md) for the roles of live Linux
references and portable hashes, independent expectations, and the rule against
including copyrighted game content in vectors. The [vector guide](VECTORS.md)
documents the format, coverage, explicit comparison differences, and regeneration
steps.

The package check verifies metadata, package files, the `py.typed` marker, and
that neither distribution contains game ROMs. It then installs the wheel into a
temporary virtual environment and imports Fernz independently of the checkout.
There is no publishing workflow.

Tests may download the Jericho corpus through `jericho_games` when needed. CI
does not cache or upload ROMs. Synthetic tests cover all eight story versions.
Real-ROM tests have a separate case for each retained game, covering V3 (16),
V4 (1), V5 (33), and V8 (6), plus Zork I metadata and mailbox/reset checks through
`FernzEnv`. V1, V2, V6, and V7 currently have synthetic coverage only. Synthetic
execution tests cover V3 arithmetic, variables, routine frames, branches,
objects, text, input suspension/resumption, dictionary parsing, and failure diagnostics.

## Black-box reference tests

Jericho 3.3.1 is pinned in the optional `reference` development dependency group
and locked with its dependencies in `uv.lock`. That group uses Python 3.11 on
Linux, keeping Jericho's native build and dependencies out of the normal Python
test matrix and Fernz's runtime dependencies. Install it and run the tests with:

```sh
sudo apt-get install --no-install-recommends frotz
uv sync --frozen --python 3.11 --group reference
uv run --no-sync poe test-reference
```

The installation requires C build tools such as `gcc` and `make`, already present
on the Ubuntu CI runners. These tests need no additional spaCy language model.
RNG comparisons also require the distribution's `dfrotz` executable; set
`FERNZ_DFROTZ` to use a separately installed binary. The reference CI job installs
the binary package and reports its version. No interpreter source is inspected.
Normal pytest runs deselect the `reference` and `rom` markers, so they neither
import Jericho nor download games. To select comparisons directly, use
`uv run --no-sync pytest -m reference -ra --tb=short`.

`tests/test_reference.py` uses only documented public `FrotzEnv` calls. It verifies
the SHA-256 of our Zork I fixture (`zork1.z5`, whose header is V3). The short
comparison runs Jericho with seed 42 and records an opening followed by `look`,
`open mailbox`, `take leaflet`, `read leaflet`, and `inventory`. A second episode
verifies repeatability after reset. Reference observations are generated during
the test, rather than committed as game text.

**The opening, mailbox, complete walkthrough, and off-path comparisons are required to pass.**
The startup comparison runs twice, with a memory mutation between resets, and
compares the transcript, score, and move count. Black-box probes of Jericho 3.3.1
showed that its observation
omits this recognized game's title line and the final prompt. Fernz retains
complete text in `Observation.stream`; its convenience `.text` omits only the
recognized trailing Zork command prompt. The Zork comparison asserts the title,
removes it for comparison, and compares the remaining text exactly, apart from
CRLF versus LF. Prompt retention in the stream is tested separately. No title
filtering or reference dependency exists in Fernz's runtime.

The off-path suite branches from **11 walkthrough checkpoints**, from the opening
through underground exploration, boat travel, and the 350-point state before the
ending. Each checkpoint runs the same **85 commands** independently, followed by
`look` and `inventory`. Inputs include unknown verbs and nouns, absent objects,
valid but futile actions such as `kick door`, incomplete commands, pronouns,
punctuation, multiple commands, container operations, and navigation. **18 longer
detours** exercise ambiguous doors, clarification replies, repeated commands,
consumables, vehicles, score changes, and continuation after recoverable death.
Each longer detour is restored and replayed exactly. Combat detours additionally
run twice with each of five seeds: 1, 12, 42, 1000, and 32767.

A dedicated death sequence takes a lit lamp into the cellar, goes south to the
chasm, and jumps. It requires the death response, a 10-point penalty, and forest
respawn, then compares continued play. Restoring the snapshot at the chasm and
jumping again must reproduce the same response and complete state. The canyon
death tests also cover repeated deaths through the terminal third fall.

Every detour turn compares the complete response, reward, score, moves, location
number, and loss/victory queries. It also requires equality of **every Fernz
snapshot field** with the converted public Jericho snapshot, including dynamic
RAM, call frames, pending input, PC, and RNG. Conversion uses only the existing
[test-only state adapter](STATE_INTEROP.md). The tests retain the documented
distinction between a recoverable death and VM quit. Failures identify the
checkpoint, command, turn, and seed; RAM failures identify differing addresses.

Separate passing tests assert two input differences rather than filtering them
out of the common command matrix:

- **Question marks:** the pinned reference replaces `?` with a space for this
  Zork build, as measured in public RAM snapshots. Fernz preserves it. The
  [Standard's section 13 remarks](https://inform-fiction.org/zmachine/standards/z1point1/sect13.html)
  explicitly identify that substitution as nonstandard. Independent synthetic
  input probes confirm that standalone Frotz preserves `?` in those stories.
  Sending the measured space-substituted input to Fernz matches both the
  reference response and its complete converted state.
- **Long lines:** Fernz's existing V3 rule reserves the terminating NUL within
  the declared buffer, accepting 99 characters for Zork's size byte of 100.
  Jericho's public input path accepts up to 198 ASCII characters here and warns
  when longer actions are truncated. Tests cover both boundaries, inspect the
  accepted bytes, and require exact response/state agreement when Jericho is
  explicitly given the same 99-character input. A synthetic standalone Frotz
  probe separately records that its dumb frontend accepts all 25 supplied
  characters despite a size byte of 20; Fernz accepts 19 and preserves the
  following canary byte. The [annotated read specification](https://zspec.jaredreisinger.com/15-opcodes#read)
  discusses the original wording's ambiguity about the V3 buffer count.

These differences do not change Fernz's runtime input handling. The required
Linux reference CI job runs all these cases without skips or expected failures.

The full walkthrough test calls `get_walkthrough()` and `seed()` to obtain the
commands and their required seed, then calls `reset()` before recording the
reference. With the pinned Jericho 3.3.1 and Zork I fixture, this is **396 commands
with seed 12**. The reference must report `victory()` and a score equal to
`get_max_score()` (**350**). Both Jericho and Fernz replay the complete sequence
after reset. Commands and transcripts stay in memory during the test; neither is
vendored into the repository. A failure identifies the episode, turn, and command.

A second full-walkthrough comparison checkpoints both interpreters before every
command, advances once, restores, and repeats the command. Both results must
match their first execution exactly, including the final quit. Jericho snapshots
are obtained and restored only through its documented public methods.

Cross-interpreter tests also transfer state after commands 35, 214, and 350,
in both directions. Only the donor plays the prefix; each recipient resumes
from converted state and completes the remaining walkthrough to 350 points.
The [test-only converter](STATE_INTEROP.md) translates the public snapshot
representation measured with independent synthetic stories. Fernz's runtime
keeps its own immutable checkpoint format and has no reference dependency.

Every turn compares text, reward, quit status, score, and move count. Fernz
retains the Enter newline that Jericho omits; tests assert and remove that
newline before comparing the remaining response. The trailing Zork command
prompt is omitted from `.text` and preserved in `.stream`.
The final turn executes `quit` and has no prompt. At that boundary only, tests
assert two observed differences: Jericho adds one trailing newline and reports
395 moves, whereas Fernz returns the story's status global of 394. Both endings
print 394 moves, as does the standalone Frotz executable. The complete remaining
ending text, reward, score, and quit status must match. The execution core stops
at `quit` without adjusting the move count. Separate profile-based outcome
queries report response events without changing that execution boundary.

There are no expected failures. A separate command-parsing comparison covers uppercase,
extra spaces, dictionary truncation, unknown words, and punctuation. Synthetic
input probes use the standalone Frotz executable, with a subprocess timeout, to
compare accepted input bytes and parse records. Overlong input and malformed
buffers are checked against the specification in the normal tests. A separate
Jericho smoke test must always pass. Score and moves are compared individually
to permit additional metadata keys.

The short mailbox sequence avoids random encounters; the full walkthrough
exercises them with its fixed seed. Separate synthetic tests require
predictable RNG sequences to match Jericho and Frotz, including counting and
large-seed modes. They run V3, V5, and V8 probes in the references; Fernz executes
the V3 probes and tests its shared generator against all three formats. See
[RNG compatibility](RNG.md) for the measured rules, evidence, and the host-seed-0
difference between the references. Expand comparisons as Fernz gains
execution, state restoration, and other public APIs. The Z-machine standard
remains authoritative when it and a reference interpreter disagree; investigate
the discrepancy instead of copying reference behavior automatically. Loading and
memory tests for all V1-V8 use independent specification-based fixtures,
since these public Jericho calls execute the game as part of initialization.

## Current scope

Work includes version-aware loading and protected memory for raw V1-V8 stories,
instruction decoding across those versions, and a V3 execution engine sufficient
to complete the measured walkthroughs for all 17 retained V3 games. The CLI can inspect any supported raw
story or play supported V3, V4, V5 and V8 stories interactively. Required ROM and Jericho tests cover
Zork's opening, mailbox sequence, full 350-point walkthrough, host reset, and
the walkthrough after an in-game restart. Additional suites exercise the
other 16 V3 routes and hundreds of detours per game; see [V3 coverage](V3_GAMES.md).
These measured routes do not establish full V3 conformance.

V4 Trinity's full winning route and detours, V5 winning routes and V8
opening/action and selected winning-route coverage are detailed in
[V4](V4.md), [V5](V5.md) and [V8](V8.md). Deferred work includes remaining
I/O features, V1/V2/V6/V7 execution, Blorb extraction, and undo. V3/V4/V5/V8
`save`/`restore` use Quetzal files through host callbacks or CLI prompts;
`restart` runs through each game's own command and confirmation flow.

## Execution foundation

Instruction decoding follows Standard §§4 and 14-15. It preserves operand types
and variable numbers without evaluating them, consumes stores before branches,
decodes signed branch offsets and inline strings, and distinguishes changing
opcode layouts by version. V6-only layouts do not apply to V7/V8. Unknown
extended opcodes in the reserved ignore range follow §14.2.1. Where §14's
`output_stream` table omits V3/V4's table operand, §§7 and 15 supply the rule.

The V3 machine uses separate routine frames with locals and evaluation stacks,
evaluates operands left to right, implements indirect stack references, and
wraps arithmetic to 16 bits. Division truncates toward zero. Array addresses
use 16-bit arithmetic and may not straddle the 64 KiB address boundary. Branch
offsets 0 and 1 return from the current routine. Routine defaults and arguments,
object links and properties, Z-strings, abbreviations, and default ZSCII output
characters are implemented independently from the standard.

V3 `jin` accepts a zero first operand as a compatibility extension: `jin 0 0`
is true, and `jin 0 n` is false for nonzero `n`. This matches standalone reference
probes and lets Zork reject `enter door` normally instead of raising an execution
error. Only this containment test treats zero as having no parent; ordinary
object access retains its validation. Required tests cover both branch
polarities and continued Zork play, including checkpoint replay against Jericho.

Zork I's boat label emits ZSCII 9 even though Standard
[§3.8.2.3](https://inform-fiction.org/zmachine/standards/z1point1/sect03.html)
defines tabs only for V6. The V3 text path accepts this legacy character as three
spaces, matching black-box Jericho transcript measurements for leading, middle,
consecutive, and trailing tabs. An independently assembled story tests both
`print_char` and encoded Z-string escapes. This compatibility extension is
confined to V3 and does not prescribe future V6 screen-layout behavior. Standalone
Frotz's screen output uses contextual spacing, so no universal tab-rendering
equivalence between frontends is claimed.

Execution runs until `sread` or `quit`, with an instruction budget to catch loops.
At `sread`, the machine has decoded the instruction and evaluated its operands,
including any stack pops. The PC points to the next instruction, and an explicit
pending input request retains the read instruction address and resolved text and
parse buffer addresses. No input has been consumed or written to those buffers.
`step()` completes that pending read and resumes execution without evaluating
its operands again.

**Design decision: keep this suspension boundary.** The Standard specifies the
behavior of `read`, but does not prescribe where a host API pauses while waiting
for input. Pausing before or after operand evaluation can both be correct.
Fernz's decoded input request separates instruction execution from input
handling and can serve interactive, structured, or asynchronous frontends.
V5 extends the request with its result variable and character-input flag while
retaining this separation; later versions can follow the same design. A checkpoint must preserve both the
post-evaluation stack and the pending request; resuming it must complete the
read exactly once before continuing at the saved PC. The test-only
[state bridge](STATE_INTEROP.md#suspended-input) translates the reference's
earlier pause point into this convention.

Output is drained after each run into an immutable `Observation`: `.text` is
the plain transcript of both windows, and `.stream` interleaves text and ordered
display commands. Geometry defaults to 80 columns by 25 rows and is configurable.
V3 advertises split-window support, but no built-in status line or variable-pitch
font. There is no screen-cell renderer or full Standard-conformance claim.
Stream 1 can be enabled or disabled, and nested stream 3 captures ZSCII in memory
without entering observations. Sound is silent when resources are unavailable.
See [observations and stream grammar](OBSERVATIONS.md) and [V5](V5.md).

Line input follows Standard [§3.7](https://inform-fiction.org/zmachine/standards/z1point1/sect03.html),
[§13](https://inform-fiction.org/zmachine/standards/z1point1/sect13.html), and
[read](https://inform-fiction.org/zmachine/standards/z1point1/sect15.html#read).
An action is one edited line without a newline. It is lowercased and translated
to default ZSCII; unrepresentable characters and control characters raise
`ValueError` before input is consumed. A non-string raises `TypeError`. V3 accepts
at most `text[0] - 1` characters, writes them from byte 1, and appends a zero.
Spaces separate words; dictionary separators are tokens themselves. Dictionary
keys use six Z-characters, with truncation and padding defined by the standard.
Parse records retain full token lengths and byte offsets, including unknown words.
Both writes are checked before either buffer changes. Invalid host input or a
nonpositive step budget can be corrected and retried at the same pending read.

Character encoding, dictionary lookup, input-buffer layout, and execution are
separate components. V5 supports counted input, token offsets starting at byte 2,
nine-Z-character keys, custom alphabet/Unicode tables, and the input result
variable. Timed input remains explicitly unsupported.

## Host reset and V3 restart

`reset()` starts a fresh episode: it restores story memory and reinitializes the
interpreter header, routine state, output, and random generator. An optional
constructor `seed` gives repeatable host-side random sequences. Positive host
seeds and predictable opcode seeds match the tested
Jericho/Frotz sequences. Explicit host seed 0 follows Frotz's deterministic
behavior; Jericho treats that constructor value as automatic seeding. With
`seed=None`, Fernz uses system entropy. The RNG component is shared across
versions; see [RNG compatibility](RNG.md).

`seed(value)` validates and returns a host seed for the next `reset()`, without
advancing execution or changing the running RNG. `random 0` and in-game restart
keep using the active episode's host seed until that reset. `seed()` and
`seed(None)` select automatic seeding and return `None`; entropy is requested
only when a reseed actually executes. Zero remains a deterministic host seed.
The constructor and setter both accept integer values in `0..2**31-1` and reject
invalid values immediately. Fernz has no automatic walkthrough-seed selection.

The V3 `restart` opcode follows Standard
[§6.1.3](https://inform-fiction.org/zmachine/standards/z1point1/sect06.html),
[§11](https://inform-fiction.org/zmachine/standards/z1point1/sect11.html), and
[restart](https://inform-fiction.org/zmachine/standards/z1point1/sect15.html#restart).
It restores the original story image and entry address, discards all routine
frames and evaluation stacks, and configures the interpreter header again.
The current Flags 2 word survives, including the fixed-font bit. The unavailable
transcription bit remains clear. It resumes execution until the next input
request or quit, within the
current call's instruction budget; a restart loop cannot renew that budget.

Per [§2.4](https://inform-fiction.org/zmachine/standards/z1point1/sect02.html),
restart leaves any opcode-seeded predictable mode and reapplies the host RNG
policy: an explicit seed repeats its sequence, while `None` requests fresh
entropy. A seed restored through `set_state()` also governs later restarts.
Host storage callbacks remain attached, and existing save files and
immutable checkpoints remain usable within the supported schema.

Already emitted text remains in the current returned observation exactly
once. The selected screen stream survives restart, matching public black-box
Frotz/Jericho probes; a story may explicitly enable it again. No host command
interception or interpreter confirmation is added: Zork asks its own question,
and the opcode executes only after the game's affirmative branch.

Required Linux reference tests exercise nested restarts and both predictable
RNG modes against Jericho 3.3.1 and standalone Frotz. Zork tests decline and
confirm restart after 35 walkthrough commands, replay a checkpoint at the
confirmation, and compare every command through the full 350-point ending.

## Host-side state checkpoints

`env.get_state()` returns a detached, immutable `GameState` after a successful
`reset()` or `step()`, including after `quit`. `env.set_state(state)` restores
it without executing any instructions or returning an observation; its return
value is `None`. A checkpoint can be reused, restored after reset or execution
failure, or loaded into a fresh environment for the same story before any reset.
The current `env.memory` object keeps its identity during restore.

`state.to_json()` and `GameState.from_json(payload, story=env.story)` provide
public, versioned JSON serialization without private-dataclass imports. Only
the current schema is accepted. See [host integration](HOST_API.md) for the
format, validation, runtime portability, and lifecycle contracts.

| Field | Meaning |
| --- | --- |
| `ram` | Immutable bytes from address zero up to the static-memory boundary, including the current header, globals, objects, and input buffers. Static story bytes are not duplicated. |
| `pc`, `frames` | Next instruction address and immutable routine records with locals, evaluation stacks, return addresses, store destinations, and supplied argument counts. |
| `input_request` | Resolved text/parse buffer addresses and instruction address for a suspended read, or `None` after quit. |
| `rng` | Generator state, counting period/position, and host seed policy. Restore consumes no entropy or random draw. |
| `screen_enabled`, `halted` | Output selection and whether the VM has executed quit. Earlier observations have already been drained and are not replayed. |
| `output` | Logical display geometry, selected window, cursors, styles, fonts, colours, buffering, and nested memory streams. Rendered cells and previous observations are not stored. |
| `game_over`, `victory` | Profile-classified loss/victory flags for the last completed response. These are independent of VM quit and preserve queries without retaining the transcript. |
| `story_sha256`, `format_version` | Identity of the original addressable story image, excluding file padding, and the Fernz snapshot schema version (currently 5). |

Memory alone is insufficient: local variables, stacks, and the execution
continuation live outside story RAM. Returned checkpoints own immutable bytes
and tuples and share no mutable execution state with the environment. Restore
checks story identity, schema version, component types and bounds, frame/input
consistency, and protected header fields before committing any change. Invalid
states raise `TypeError` or `ValueError` and leave the current episode intact.
These checks establish structural validity, not that arbitrary edited RAM is a
meaningful game position. Obtain checkpoints through `get_state()`.

Host checkpoints include RNG and output settings for reproducible exploration.
The restored host seed also controls subsequent `reset()`, `random 0`, and `restart` calls.
With host seed `None`, restoring preserves the current random sequence, but a
later reset, `random 0`, or restart still obtains fresh entropy. Use an explicit seed for
replays that include reseeding.

The pending next-reset choice from `seed()` is environment configuration, outside
the checkpoint. `set_state()` restores the checkpoint's active
host seed and uses that for future resets, replacing any pending choice.

This API follows Jericho's public save/restore workflow using Fernz's own state
representation. Jericho's API page documents a seven-entry tuple; black-box
inspection of the returned value in 3.3.1 shows nine entries. Its first entry is
an unsigned-byte array containing 11,859 bytes for our Zork I story, matching the
dynamic-memory boundary. Fernz exposes those bytes as `state.ram`; it does not
accept Jericho tuples directly. The [test-only state bridge](STATE_INTEROP.md)
converts V3 input-boundary snapshots in both directions for the pinned Linux
reference, including memory, frames, input continuation, and RNG state. It
supplies a placeholder for the missing prior observation on export.

These checkpoints support V3, V4, V5 and V8 and retain a separate contract from
story-level `save`/`restore` and their Quetzal files. Standard
[§6.1](https://inform-fiction.org/zmachine/standards/z1point1/sect06.html)
defines the VM's saved state and special header-restoration rules; its remarks
exclude RNG and I/O settings from that state. Host checkpoints instead restore
the complete captured environment, including Flags 2. Host callbacks and their
external storage belong to the recipient and are not captured or rewound.

## Environment copies and status queries

`copy()` creates an independent environment at the same execution boundary,
including after quit. Memory, frames, stacks, and RNG are independent; the
immutable story is shared. Copying executes no instructions, emits no text,
requests no entropy, and does not reread the original file. An environment that
has not initialized, or has failed execution, stays uninitialized in its copy
and needs `reset()` or `set_state()` before play. Loading-only copies also work
for story versions whose execution is not yet supported.

Copies retain references to the configured storage callbacks. External files and
callback closure state remain owned by the caller. Forking VM memory does not
duplicate those resources. Copies also preserve both the active RNG host seed
and the pending next-reset seed; see the documented [Jericho copy/seed
difference](RNG.md#host-seeding-and-reset).

`get_score()` and `get_moves()` use measured profile globals and widths for
all 17 retained V3 builds, falling back to the V3 status convention for
unprofiled score-based games. Both read live state without advancing execution
or altering snapshots, and work after quit. They agree with the values in
`reset()` / `step()` info, including after restoration and restart. Construction
and execution failure require a successful reset or checkpoint restore first.
Unprofiled time-based V3 games raise `NotImplementedError` for these queries.
See [V3 games](V3_GAMES.md) for the profiled time-game conventions.

The required reference job forks Zork after command 35, compares the copy's
remaining walkthrough and status queries with Jericho through the ending, and
verifies that both original environments remain unchanged. The known final
move-count difference remains explicit: Fernz reads 394 from the story, while
Jericho reports 395. Further checks query status after save, restore, restart,
reset, and host checkpoint restoration.

## Object inspection, locations, and story outcomes

`get_object(n)`, `get_world_objects(clean=False)`, `get_player_object()`, and
`get_inventory()` provide detached, locally mutable `ZObject` snapshots for V3.
Fields include full names, parent/sibling/child links, attributes, and property
numbers. Direct lookup and enumeration infer the object count from the original
story's table layout; unsupported layouts raise `NotImplementedError`. Player
and inventory queries require a known player profile. `clean=True` is deferred.
See [object inspection](OBJECT_INSPECTION.md) for contracts, traversal examples,
reference differences, and required CI coverage.

`get_player_location()` now returns the same complete `ZObject` snapshot type,
retaining the existing `.num` and `.name` fields.
All retained V3 profiles use the known player's immediate parent, including
vehicles; unprofiled V3 stories use the status-line location global. Names retain the complete
decoded story short name. Zero returns `None`; malformed object data raises
an error without advancing the game.

Exact story-image profiles supply all 17 V3 builds' `get_max_score()` and
response-based `game_over()` / `victory()` queries. Unknown builds raise
`NotImplementedError` for these metadata/outcome queries. Location and outcome
queries require initialized state; the static score limit is available as soon
as the story is loaded.

Public probes show that Zork's first two canyon deaths report loss while still
allowing play, and a later ordinary response clears it. Victory is reported on
entering the barrow, rather than merely reaching 350 points. Voluntary quit
reports neither. Fernz keeps VM `done` separate from these response events and
stores the two flags in checkpoints so copy/restore preserve them.
No transcript is retained. See [story queries](STORY_QUERIES.md) for the profile
identity, evidence, name differences, and required CI coverage.

## Story-level save and restore

V3 `save` and `restore` now execute through optional host storage callbacks.
The codec follows the published Quetzal specification, writes compressed memory,
and reads both compressed and uncompressed saves. Restore checks file structure,
story identity, memory, frames, and the saved branch before committing changes.
Successful restore resumes the saved `save` instruction's successful branch;
failure returns false through the current `restore` instruction's branch.

Opcode restore preserves the current RNG, output selection, and Flags 2, and
sets interpreter-owned header fields for Fernz. It does not alter the existing
deterministic `get_state()` / `set_state()` contract. No RNG extension is written
to Quetzal files. See [save/restore design and usage](SAVE_RESTORE.md) for the
storage callbacks, CLI behavior, validation rules, and specification links.

Required reference tests exchange Quetzal files with standalone Frotz using
nested-call probes (including PCs above 64 KiB) and Zork I. They also insert
save/restore operations after walkthrough commands 35, 214, and 350, change score
memory before restoring, and compare every gameplay turn to the uninterrupted
Jericho trace through the 350-point ending. Synthetic tests cover file-format
vectors, failure and cancellation, branch polarity and returns, malformed-file
rejection, current RNG preservation, and unchanged host checkpoint behavior.

## Story loading and memory

```python
from fernz import Memory, Story

story = Story.from_file("games/zork1.z5")
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
not be aligned. Reads cover the whole logical image for instruction and string
access; opcode-specific addressing limits belong to the execution layer.
Corresponding write methods reject out-of-range values, writes outside dynamic
memory, and changes to protected header bits or extension words. Only the
game-writable Flags 2 bits are allowed in the header. Invalid multi-byte writes
leave all bytes unchanged. Errors raise `MemoryAccessError` (a `ValueError`).

`memory.copy()` copies current contents independently. `memory.reset()` restores
the original image exactly. This low-level reset is not VM restart or save
restoration. `FernzEnv.reset()` and `set_state()` also manage CPU and interpreter
state; opcode restoration and restart apply their own header rules. No writable
memory views are exposed.

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
`ExecutionError`, `UnsupportedOpcodeError`, `GameState`, `Observation`, `ZObject`, and `FernzEnv` from `fernz` for the public library
interface and `fernz` or `python -m fernz` for the public CLI.
`fernz --inspect GAME` prints JSON metadata and exits with 0. It reports both
physical file size and logical story size, plus checksum validity (null when
unavailable). A checksum mismatch is reported as false without rejecting the
inspection. Help exits with 0; missing/invalid arguments, paths, or story formats
exit with 2. `fernz GAME` writes the complete transcript and reads one command per
line until quit or EOF, then exits with 0. Ctrl-C exits with 130. Unsupported
execution versions, unimplemented opcodes, invalid input or execution, and budget
exhaustion report an error on stderr and exit with 1. The CLI delegates to the
public library and also accepts piped commands. In-game SAVE/RESTORE prompts
consume a filename from the same input stream; a blank line or EOF cancels.
Save asks before overwriting and replaces the file only after a complete write.
Filesystem errors are reported on stderr and return opcode failure to the game.

The deliberately small public contract is:

| Interface | Contract |
| --- | --- |
| `from fernz import FernzEnv` | Public environment class; no Jericho runtime dependency. |
| `FernzEnv(game_path, *, seed=None, save_handler=None, restore_handler=None, screen_width=80, screen_height=25)` | Accepts a string or text path-like object, stores a `Path` in `game_path`, and loads a raw V1-V8 story without executing it. Missing/inaccessible paths raise `OSError` subclasses; non-regular paths raise `ValueError`; invalid story data raises `StoryFormatError`. Optional synchronous callbacks supply storage; see [save and restore](SAVE_RESTORE.md). |
| `env.story`, `env.memory` | Immutable story image and independent protected memory instance. |
| `FernzEnv(story, **options)` | Reuse a loaded `Story` without file I/O or opening execution, with independent memory and the same options as path construction. `game_path` is `None`. |
| `env.reset(*, max_steps=1_000_000)` | Run fresh V3 startup through input or quit and return `(observation: Observation, info: dict[str, object])`. The observation provides a plain transcript and an ordered display stream; see [its contract](OBSERVATIONS.md). Score games expose integer `score` and `moves`; time games expose `hours` and `minutes`. |
| `env.seed(seed=None)` | Validate and return `int` in `0..2**31-1`, or `None` for automatic seeding, to apply on the next host reset. Does not change the active episode. An omitted argument selects automatic seeding. |
| `env.copy()` | Fork mutable execution state and both active/pending seed policies without executing or reading files. Share immutable story data and host callback references. |
| `env.get_score()`, `env.get_moves()` | Read the current V3 score and move-count globals as integers, including after quit. Require initialized state; time-based status games raise `NotImplementedError`. |
| `env.get_max_score()` | Read the exact story profile's score limit, including before reset. Unknown story images raise `NotImplementedError`. |
| `env.get_object(obj_num)` | Return a detached `ZObject` or `None` for an absent number, including zero. Require initialized V3 state and an enumerable initial layout. |
| `env.get_world_objects(clean=False)` | Return a list of detached objects indexed by number, with an empty slot zero. Include disconnected and unnamed objects. Require initialized V3 state and an enumerable initial layout; `clean=True` raises `NotImplementedError`. |
| `env.get_player_object()`, `env.get_inventory()` | Return the known player object, or a list of its immediate children in sibling order. Require initialized state and a known player profile. |
| `env.get_player_location()` | Return a complete detached `ZObject` or `None` for location zero. Use the known player's immediate parent when profiled, otherwise the V3 status location. Require initialized state; preserve full story short names. |
| `env.game_over()`, `env.victory()` | Read loss/victory flags classified from the last completed response. Require initialized state and a supported story profile. Copies and checkpoints retain these flags independently of VM quit. |
| `env.step(action: str, *, max_steps=1_000_000)` | Complete a pending V3 read and return `(observation: Observation, reward: int, done: bool, info: dict[str, object])`. Reward is the signed score delta, or zero for time games. The observation contains only new output; `.stream` retains prompts and `.text` omits the recognized Zork command prompt. |
| `env.get_state()` | Return an immutable `GameState` after reset, step, or a successful restore. Raises `RuntimeError` before initialization or after execution failure. |
| `env.set_state(state)` | Validate and restore a Fernz checkpoint for the same story, including RNG and host seed; return `None`. May be called before reset, after quit, or after execution failure. Invalid input leaves the environment unchanged. |
| `state.to_json()`, `GameState.from_json(payload, *, story)` | Encode or validate/decode a portable JSON string; retain all checkpoint fields, use base64 only for RAM, and exclude callbacks. See [host integration](HOST_API.md). |
| `env.initialized` | True when an execution context exists, including after quit; false before initialization or after execution failure. |
| `env.done` | True after the VM executes `quit`; false before reset. It does not infer death or victory while the story is still running. |
| `env.awaiting_character` | True when a live interpreter is waiting for a single keypress (`read_char`); false at a line prompt, before reset, after quit, or after execution failure. |
| `env.close()` | Idempotent resource cleanup; currently a no-op because no resources are held. |

The tuple shapes follow the permitted
[Jericho public quickstart](https://jericho-py.readthedocs.io/en/latest/tutorial_quick.html).
Unsupported execution versions raise `NotImplementedError`. Legal but unsupported
instructions raise `UnsupportedOpcodeError`, a `NotImplementedError` subclass,
with the opcode and address. Invalid instructions, runtime errors, and budget
exhaustion raise `ExecutionError`, a `RuntimeError` subclass. A failed episode
should be reset or restored from a valid checkpoint before reuse. This is not a claim of drop-in Jericho
compatibility.
Calling `step()` before a successful reset or restore, after quit, or after
execution fails raises `RuntimeError`; reset or restore a runnable checkpoint.

The [Cabin Fever compatibility audit](CABIN_FEVER_COMPATIBILITY.md) covers the
server, standalone player, and custom snapshot persistence at a pinned consumer
revision. Fernz now provides maximum score, location objects with stable numbers
and full names, and loss/victory queries for all retained V3 builds, alongside
its existing V3 interaction and score/move queries. The target is future
integration: Cabin Fever may change its calls and
adopt a new save format based on Fernz's immutable checkpoints. Importing existing
`.bin` saves and preserving their tuple layout are out of scope. Its optional
change of RNG trajectory on server reload needs an explicit adapter policy,
preserving deterministic Fernz checkpoint restoration. The audit records every
call, behavioral gaps, and CI acceptance requirements. Private native-library
access remains outside the public contract; the consumer's two such calls
require public replacements.

API tests use temporary synthetic files without requesting the game fixture
or downloading ROMs. Package validation also exercises the installed command and
module entry point from a temporary directory outside the checkout.

## Additional V3 games

[V3 gameplay coverage](V3_GAMES.md) documents the other 16 complete routes,
per-game profiles, live and portable detours, loss and lifecycle scenarios,
maze/current/timing checks, and explicit reference limitations. The earlier
Zork milestones above remain part of the required core suite.


## Complete retained V5 routes

The [V5 coverage document](V5.md#complete-retained-v5-winning-routes) records
winning routes and exact-image query profiles for all 33 retained V5 stories.
The additional 30 routes add 6,655 commands with live public Jericho comparisons
on Linux and hashed portable vectors elsewhere. Every step checks world objects,
player, location, inventory, counters, outcomes, input and RNG. Display geometry,
character-pause text grouping, reference truncation, and terminal-state exceptions
are explicit in the tests and documentation. Three V5 groups keep this work in
the manual comprehensive workflow; the fast PR workload remains bounded.

### V8 milestones

V8 execution reaches all six retained opening screens and continues through
commands, snapshots, save/restore and restart. It shares V5 semantics with
eight-byte packed addresses and file-length units. High-address synthetic
tests and public-reference hashes cover those scenarios, plus full winning
routes and query APIs for all six games. See [V8 compatibility](V8.md)
for exact scope, counter probes and startup pause conventions.

## Static type checking

`uv sync --frozen` installs the locked developer tools, including Pyright and
Textual. Run `uv run --no-sync poe typecheck` for just types, or
`uv run --no-sync poe check` for formatting, lint, spelling, and types together.
Both automatic PR CI and the manual comprehensive workflow run the latter.
Textual remains an optional runtime extra; its development installation lets
Pyright check the frontend against the real library declarations.

Pyright uses **strict** mode, Python 3.11 (the minimum supported language
version), and the local `.venv`. It checks every module in `src/`, including
both CLIs, plus `tests/typing/` consumer examples. There are no package-file
exclusions or blanket diagnostic ignores. Runtime tests and maintenance scripts
are outside this initial static scope: they include deliberately malformed API
inputs and optional black-box reference integrations. They retain linting and
runtime validation; this is not a claim that the test harness is strictly typed.
Two strict diagnostics are disabled deliberately: `reportPrivateUsage`, because
private package modules cooperate through internal helpers, and
`reportUnnecessaryIsInstance`, because public boundaries must still reject bad
values from untyped callers. Unknown types and missing generic parameters remain
errors. JSON decoding uses `object`, checks scalar/container types explicitly,
and retains checkpoint range and story validation before returning a state.

The public `ResetResult`, `StepResult`, and `StatusInfo` aliases name existing
return shapes. `StatusInfo` deliberately retains `dict[str, object]` compatibility
for callers that annotate or extend their metadata; Fernz itself supplies integer
status globals. `Cursor`, `ColourPair`, `MemoryStream`, and `PythonRandomState`
name nested checkpoint values. These are aliases, not replacement runtime
classes: tuple layouts, mutable dictionaries, checkpoint schemas, and wire
formats remain unchanged. No public API break is required.
