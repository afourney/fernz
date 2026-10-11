# Portable Zork I reference vectors

`tests/vectors/zork1_vectors.zip` records expectations from public Jericho 3.3.1
calls on little-endian Linux/Python 3.11. Python's standard `zipfile` library
reads its JSON members into memory; replay never extracts the archive to disk
and requires neither Jericho nor NumPy. This supplements the live Linux
reference tests. There is no automatic fallback when a reference is missing.

The clean-room requirement applies to recording and maintenance: use the
Z-machine specification, public API documentation, and executable behavior.
Do not inspect Jericho or Frotz implementation source.

## Contents and coverage

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
not claim to replace every Linux reference test or cover other games.

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
from the repository root. It also accepts `--story /path/to/zork1.z5` to use an
existing matching ROM and `--output /path/to/zork1_vectors.zip` to record or check
another archive. For example:

```sh
uv run --no-sync python -m tests.scripts.generate_zork1_vectors --check
```

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
the committed ZIP against fresh public reference runs, and replays it.
An additional Python 3.12 matrix runs the ordinary offline suite and portable
vectors on `macos-latest`, `windows-2025` (x64), and `windows-11-arm`.
Those jobs explicitly check that Jericho is not installed. They download the
ROM fixture independently and do not cache or upload game files.

GitHub's standard hosted x64 Windows image is Windows Server 2025; the ARM
image is Windows 11. See the [hosted runner labels](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
