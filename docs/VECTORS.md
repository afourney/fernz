# Portable test vectors

Our [testing philosophy](TESTING_PHILOSOPHY.md) explains the roles of live
references and recorded hashes, independent expectations, and the rule against
including copyrighted game content in vector archives.

`tests/vectors/<rom>_vectors.zip` records each V3 game's expectations from public Jericho 3.3.1
calls on little-endian Linux/Python 3.11. Python's standard `zipfile` library
reads JSON members into memory; replay never extracts the archives to disk
and requires neither Jericho nor NumPy. This supplements the live Linux
reference tests. There is no automatic fallback when a reference is missing.

The clean-room requirement applies to recording and maintenance: use the
Z-machine specification, public API documentation, and executable behavior.
Do not inspect Jericho or Frotz implementation source.

## Story file metadata

`tests/vectors/storyfiles.zip` contains **58 JSON members**: one manifest and
one metadata record for each of the **57 retained ROMs**. It occupies about
**39 KB** compressed. The explicit inventory is shared with the original
loading tests in `tests/story_corpus.py`: V3 (17), V4 (1), V5 (33), and V8 (6).

These expectations come directly from the original file bytes and Standard
1.1's header table, length units, and checksum definition. The metadata recorder
does not use Fernz's story parser or execute the games. Its limited decoder
covers the versions present in this corpus; synthetic tests retain V1, V2,
V6, and V7 loading coverage.

Every record pins the whole file's SHA-256, physical and addressable sizes,
all public header fields, entry point, packed-address scale, header extension
words, and checksum. SHA-256 fingerprints cover the complete memory image,
dynamic memory, static memory, and globals. The ZIP stores metadata and hashes,
without bundling ROMs or memory dumps.

There are two portable cases per story: one compares the loader and memory
against these expectations, including isolated writes, copying, reset, and
read-only/bounds enforcement; the other checks environment construction and
the CLI's `--inspect` JSON. This adds **112 portable tests** alongside the gameplay tests. It checks loading and metadata across all versions in the corpus,
without claiming execution support beyond V3. Missing files, changed ROM
identities, missing archive records, or incomplete corpus coverage fail.

The existing direct ROM smoke tests remain available through `poe test-roms`.

## Zork I gameplay

The archive contains **38 JSON members**, **965 cases**, and **3,494 recorded
boundaries**, occupying about **350 KB** compressed:

| Members | Contents |
| --- | --- |
| 1 | Manifest: format version, reference version/platform, ROM SHA-256, checkpoint locations, and member checksums/counts. |
| 1 | Complete 396-command winning walkthrough plus its opening, seed 12. |
| 11 | 85 independent three-command detours at each checkpoint, followed by `look` and `inventory`. |
| 22 | Longer parser, container, vehicle, exploration, wait/current, and recoverable-death scenarios. |
| 1 | Cellar-to-chasm death and continued play. |
| 1 | Save, rejected restart, confirmed restart, restore, and continued play. |
| 1 | Combat at seeds 1, 12, 42, 1000, and 32767, including each opening. |

Each boundary contains the command, reward, reference done flag, score/moves,
outcome flags, and hashes of the observation and object queries. Pending-input
boundaries also contain a canonical VM fingerprint: SHA-256 of dynamic RAM and
frames, plus PC, input continuation, RNG, story identity, screen-stream selection,
and outcome flags. Its `state_format_version=2` identifies the reference-visible
projection, not the current public checkpoint schema (5). Window geometry,
cursors, fonts, styles and colours are excluded because public native snapshots
do not expose them. Full Fernz snapshot replay separately checks those fields. The test-only
[state bridge](STATE_INTEROP.md) converts the public native snapshot when
recording; portable replay compares Fernz's snapshot without loading that bridge.

The object fingerprint hashes the raw world list, inventory, player, and
location, including names, links, attributes, and property numbers. These
SHA-256 checks are test expectations, not an implementation of Jericho's
`get_world_state_hash()`. Known [object name and unnamed-node differences](OBJECT_INSPECTION.md)
are handled explicitly by the test helper. RAM checks still cover unnamed nodes.

The ZIP includes commands and metadata, but no ROM, narrative, object names,
raw RAM, stack dump, or saved-game payload. ROMs remain separate, untracked
fixtures with their existing distribution terms. Replay uses `jericho_games`,
which downloads the existing public corpus only if `games/` is absent, and
requires the exact pinned Zork I SHA-256 and header version 3.

The tests play the walkthrough to build their own checkpoints, replay every
walkthrough continuation from a snapshot, replay each detour twice, verify
deferred seeds through combat resets, and check independent copies and detached
object snapshots. Save/restore uses temporary in-memory host storage. Native
snapshot and Quetzal interchange with other interpreters remain live Linux
tests; hashes cannot be imported as a saved game.

## Explicit comparison boundaries

Presentation handling follows the existing live tests: select `Observation.text`,
assert Fernz's title and input newline, then hash the corresponding reference
observation. The recognized Zork trailing command prompt is already omitted from
`.text`; separate tests require it in `.stream`.
Line endings normalize only CRLF to LF. The restart confirmation's trailing
space/prompt and the winning ending's final newline have separate modes.

At the winning quit, Fernz reports the story's 394 moves and Jericho reports
395. That exact difference is asserted. Full canonical-state comparison stops
at the last pending input because the measured bridge does not translate
halted native states; the ending still compares output, reward, status,
outcomes, and object queries. A recoverable death is a reference `done` outcome
but leaves Fernz runnable. These cases do not loosen ordinary comparisons.

Question-mark substitution, overlong input, synthetic reference probes, and
terminal-death differences retain their existing live tests. This corpus does
not claim to replace every Linux reference test. The additional archives cover
the remaining retained V3 games as described below.

## Other V3 games

Each of the other 16 ROMs has `<rom stem>_vectors.zip`, including
`zork2_vectors.zip` and `zork3_vectors.zip` despite their misleading `.z5`
filenames. The 15 reference-bound games have nine JSON members: manifest,
full walkthrough, five detour checkpoints, scenarios, and seeds. LGOP has six
members with its own public-snapshot recorder and partial female routes; see
[LGOP coverage](LGOP.md). The 17 V3 gameplay archives together occupy about
**2.6 MB** compressed and hold over **27,000 gameplay boundaries**. See
[V3 games](V3_GAMES.md) for exact seeds, maximum scores, player identities,
coverage, independent object expectations, and narrow comparison differences.

## Run and regenerate

On any supported platform, with the normal development dependencies:

```sh
uv sync --frozen --python 3.12
uv run --no-sync poe test-vectors
```

On little-endian Linux, install the pinned reference dependency and explicitly
regenerate after investigating the intended change:

```sh
uv sync --frozen --python 3.11 --group reference
uv run --no-sync poe generate-vectors
uv run --no-sync poe check-vectors
uv run --no-sync poe test-vectors
```

The helper is `tests/scripts/generate_vectors.py`. Invoke it as a module
from the repository root. Generation and checking process **all 17 archives by default**. Use
`--only zork1`, `--only storyfiles`, or another ROM stem to select one.
`--only v3` selects the 15 additional games; `--v3-shard 1/3` selects five.
`--output-dir` changes the additional gameplay archives' destination.
Story metadata can be generated and checked on any platform, without Jericho:

```sh
uv run --no-sync python -m tests.scripts.generate_vectors --only storyfiles
uv run --no-sync python -m tests.scripts.generate_vectors --only storyfiles --check
```

`--suite /path/to/jericho-game-suite` selects an existing corpus. If omitted,
the existing download fixture supplies it. `--story /path/to/zork1.z5` can
override the Zork gameplay ROM. `--output /path/to/zork1_vectors.zip` selects
the gameplay archive destination; `--storyfiles-output /path/to/storyfiles.zip`
selects the metadata archive destination. These options also apply to `--check`.

Generation uses only the public reference for expected execution results;
it does not run Fernz to bless its current behavior. Scenario definitions and
explicit compatibility rules are shared with the live comparisons. The public
walkthrough is retrieved from Jericho each time. Reference SAVE writes inside
an automatically removed temporary directory.

Members use sorted compact JSON, a fixed timestamp, fixed permissions, and
DEFLATE compression. Writes replace the complete archive atomically.
`--check` regenerates in memory and compares every decoded member, reporting
changed member names without modifying the ZIP. It compares content rather
than compressed bytes so zlib differences cannot create false failures.
Missing dependencies, wrong ROMs, unsupported formats, missing members,
checksum/count mismatches, and changed expectations fail the run.

When a hash fails, pytest identifies the scenario, action, and differing
fingerprint field. Observation failures also show Fernz's actual text. Reproduce
that case in the live Linux tests to inspect reference data; do not regenerate
simply to make a failure disappear. Changes to the record contract require a
vector format version change and coordinated reader/generator updates.

## CI

V5 coverage adds `905_vectors.zip`, generated with
`poe generate-vectors --only 905` and verified with `poe check-vectors --only 905`.
It contains a bounded opening/five-command prefix for fast CI and full
walkthrough, detour, lifecycle, and seed cases for comprehensive CI. V5 record
schema 3 adds status, outcome, RNG, and object-query fingerprints; the common
ZIP manifest envelope remains format 1. See [V5 milestones](V5.md).

Every PR runs the offline suite, all 57 story files' loading and inspection
checks, and bounded gameplay prefixes for all 17 V3 games. It verifies every
archive member's integrity and compares short live traces on Linux. Short
portable replay runs on macOS and both Windows runners without Jericho.
See [fast and comprehensive CI](CI.md) for timing limits and manual dispatch.

In the manual comprehensive workflow, the core Linux reference job keeps
existing comparisons, checks Zork I and
story metadata archives, and replays those vectors. Three additional Linux
jobs partition the other 15 games and run live comparisons plus archive
freshness checks. The Python 3.12 portable matrix has a core group and the
same three V3 groups on `macos-latest`, `windows-2025` (x64), and
`windows-11-arm`. Core runs the ordinary offline suite too. Every portable
job verifies Jericho is absent. ROM fixtures are downloaded independently
and are never cached or uploaded as artifacts.

GitHub's standard hosted x64 Windows image is Windows Server 2025; the ARM
image is Windows 11. See the [hosted runner labels](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

## V5 corpus startup

All 33 retained V5 ROMs have a `breadth.json` member in their own
`<rom>_vectors.zip`: 66 scenarios and 396 boundaries in total. These breadth scenarios remain alongside the full-route records. Each manifest pins the ROM and reference version and hashes its JSON
members. The companion live tests use the same replay assertions with fresh
measurements. See [V5 phase 2](V5.md#broader-v5-validation-phase-2) for startup
keys, reference conventions, measured presentation rules, and coverage limits.

Use `poe generate-vectors --only v5` to regenerate the group. The default
regeneration includes these archives; `--only <rom>` selects one. Both the live
suite and `poe check-vectors --only v5` are mandatory in the manual V5 CI job.
Portable CI runs without Jericho or NumPy on each supported hosted OS.

Balances and Sherlock extend their existing archives with complete trajectories,
profiled query hashes, detours, loss paths, persistence and seeded forks. Their
`breadth.json` members remain unchanged, so corpus startup checks keep their
original scope. Boxed clue text has a separate upper-window hash checked through
the public display stream; no clue text or object names enter the archives. See
[V5 phase 3](V5.md#broader-v5-validation-phase-3) for display and input boundaries.


## Complete V5 route vectors

The remaining 30 archives now contain `manifest.json`, `breadth.json`,
`walkthrough.json` and `counters.json`. They cover 6,655 walkthrough commands,
with hashed text, object/property bytes, globals, raw world/player/location/
inventory records, and numeric query results. Counter probes independently
establish signedness and byte/word widths. Manifests pin screen geometry as well
as story identity, seeds, reference version and member hashes. State is checked
at each input boundary even when a text hash spans character-input pauses.

See [complete V5 coverage](V5.md#complete-retained-v5-winning-routes) for narrow
reference presentation rules, truncated object enumeration, and the explicit
Deephome/Murdac ending differences. Generation uses public Jericho calls and
specification-based decoding of public snapshots; Fernz execution is never the
expected-result oracle. Only hashes and metadata are committed, with no story
narrative, object names, ROM bytes, RAM/stack dumps or save files.

The same `--v5-shard 1/3` selector partitions live tests, portable tests and
`generate-vectors` / `check-vectors --only v5`. The long routes remain manual;
automatic CI continues to check archive integrity without executing them.
The 33 V5 ZIPs together occupy about 1.75 MB (1.67 MiB).

## V8 vectors

All six retained V8 games have `<rom>_vectors.zip` archives containing opening
and action/persistence records, plus `walkthrough.json` and `counters.json`.
Their complete winning routes cover 966 inputs at explicit seed 42. Together
the six ZIPs occupy about 250 KiB; they contain no narrative, ROM bytes, RAM
dumps or save payloads. See [the corpus inventory](CORPUS.md) for each route.

Each step hashes object entries/property tables and all 240 global words,
and records RNG and pending input facts. Opening/action text is checked per
step; full-route text is grouped across character pauses to account for the
reference's deferred words. V8 record version 2 records these boundaries and
the measured first-character clipping. Full routes also hash complete object,
player/location and inventory query results, with counters, rewards and outcomes.
The recorded raw reference outcomes remain available alongside Fernz's documented
winning-menu interpretation. Counter probes test width and signedness separately
from ordinary small gameplay scores.

Regenerate or verify the entire group with `--only v8`, or select `--only lostpig`
and another ROM stem individually. Comprehensive Linux jobs compare public
reference behavior directly and check archive freshness; the V8 portable jobs
run the same assertions without Jericho. Full walkthroughs stay outside fast PR
checks. See [V8 compatibility](V8.md) for exact coverage and presentation rules.

## V4 Trinity

`trinity_vectors.zip` contains the 610-command winning route at seed 0, 318 parser
branches across six checkpoints, a loss sequence, lifecycle scenarios, three
alternate-seed prefixes and counter-width probes. Its seven members store
commands, numeric measurements and hashes only. Comparisons cover both windows,
all dynamic RAM outside the header, RNG, input boundaries and public query APIs.
See [V4 compatibility](V4.md) for the exact presentation and outcome conventions.

Regenerate with `poe generate-vectors --only trinity` in the Linux Python 3.11
reference environment; `--check` or `poe check-vectors --only trinity` validates
freshness. `--only v4` selects the same archive. Fast CI replays only the opening
and five commands; comprehensive V4 jobs replay all records on every platform.

LGOP uses the same hashed ZIP envelope with an independently exercised route,
Tiffany partial routes, and a public-snapshot oracle for its unbound reference
queries. See [LGOP coverage and regeneration](LGOP.md).
