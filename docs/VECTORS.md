# Portable test vectors

Our [testing philosophy](TESTING_PHILOSOPHY.md) explains the roles of live
references and recorded hashes, independent expectations, and the rule against
including copyrighted game content in vector archives.

`tests/vectors/zork1_vectors.zip` records expectations from public Jericho 3.3.1
calls on little-endian Linux/Python 3.11. Python's standard `zipfile` library
reads JSON members into memory; replay never extracts the archives to disk
and requires neither Jericho nor NumPy. This supplements the live Linux
reference tests. There is no automatic fallback when a reference is missing.

The clean-room requirement applies to recording and maintenance: use the
Z-machine specification, public API documentation, and executable behavior.
Do not inspect Jericho or Frotz implementation source.

## Story file metadata

`tests/vectors/storyfiles.zip` contains **57 JSON members**: one manifest and
one metadata record for each of the **56 retained ROMs**. It occupies about
**39 KB** compressed. The explicit inventory is shared with the original
loading tests in `tests/story_corpus.py`: V3 (16), V4 (1), V5 (33), and V8 (6).

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
the CLI's `--inspect` JSON. This adds **112 portable tests** to the 967 Zork
tests. It checks loading and metadata across all versions in the corpus,
without claiming execution support beyond V3. Missing files, changed ROM
identities, missing archive records, or incomplete corpus coverage fail.

The existing direct ROM smoke tests remain available through `poe test-roms`.

## Zork I gameplay

The archive contains **35 JSON members**, **962 cases**, and **3,474 recorded
boundaries**, occupying about **344 KB** compressed:

| Members | Contents |
| --- | --- |
| 1 | Manifest: format version, reference version/platform, ROM SHA-256, checkpoint locations, and member checksums/counts. |
| 1 | Complete 396-command winning walkthrough plus its opening, seed 12. |
| 11 | 85 independent three-command detours at each checkpoint, followed by `look` and `inventory`. |
| 19 | Longer parser, container, vehicle, exploration, and recoverable-death scenarios. |
| 1 | Cellar-to-chasm death and continued play. |
| 1 | Save, rejected restart, confirmed restart, restore, and continued play. |
| 1 | Combat at seeds 1, 12, 42, 1000, and 32767, including each opening. |

Each boundary contains the command, reward, reference done flag, score/moves,
outcome flags, and hashes of the observation and object queries. Pending-input
boundaries also contain the complete canonical snapshot fingerprint: SHA-256
of dynamic RAM and frames, plus PC, input continuation, RNG, story identity,
screen selection, and snapshot flags/version. The test-only
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

Presentation handling follows the existing live tests: assert Fernz's title,
input newline, and prompt, then hash the corresponding reference observation.
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
not claim to replace every Linux reference test or execute other games.

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

The helper is `tests/scripts/generate_zork1_vectors.py`. Invoke it as a module
from the repository root. Both generation and checking now process **both
archives by default**. Use `--only zork1` or `--only storyfiles` to select one.
Story metadata can be generated and checked on any platform, without Jericho:

```sh
uv run --no-sync python -m tests.scripts.generate_zork1_vectors --only storyfiles
uv run --no-sync python -m tests.scripts.generate_zork1_vectors --only storyfiles --check
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

The required Linux reference job keeps all existing live comparisons, checks
both committed ZIPs against fresh reference/specification measurements, and
runs both portable suites.
An additional Python 3.12 matrix runs the ordinary offline suite and portable
vectors on `macos-latest`, `windows-2025` (x64), and `windows-11-arm`.
Those jobs explicitly check that Jericho is not installed. They download the
ROM fixture independently and do not cache or upload game files.

GitHub's standard hosted x64 Windows image is Windows Server 2025; the ARM
image is Windows 11. See the [hosted runner labels](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
