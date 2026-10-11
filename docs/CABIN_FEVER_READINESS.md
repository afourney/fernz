# Cabin Fever x86 readiness review

Reviewed **2026-10-11** against:

- Fernz [`d6e7aa2`](https://github.com/afourney/fernz/tree/d6e7aa2de83004790c599622b7c9c90ddb8caff2),
  the `main` revision preparing version 0.0.1.
- Cabin Fever x86 [`b4933c8`](https://github.com/afourney/cabin-fever-x86/tree/b4933c8b167635c9ffbd7cd8ffd1307fc0b3d52e),
  its current `main` at review time. Its lockfile selects Jericho 3.3.1.

## Assessment

**Fernz is ready for a focused Cabin Fever integration effort, starting with
Zork I. It is not yet an operational replacement in the unmodified application.**
The core interpreter and most of the query surface Cabin Fever actually uses
are implemented and have substantial gameplay coverage. The immediate work is
primarily in the consumer: translating observations, choosing consistent episode
semantics, connecting new checkpoints to autosave/resume, and handling failures.

A general replacement for the entire downloaded library needs additional input
handling and game-capability work. Four V8 games still lack the story profiles
that support Cabin Fever's mapping and status features. A game reaching its
opening prompt is not sufficient evidence that Sam can play it reliably.

| Intended use | Readiness judgment |
| --- | --- |
| Begin a Zork I integration branch | **Go.** No missing core execution or required story-query capability was identified for the pinned build. |
| Ship a Zork I pilot to users | **Not yet.** Complete the consumer changes and end-to-end acceptance checks below. |
| Replace Jericho across the 57-game library without restrictions | **Not yet.** Resolve startup/input handling, unsupported metadata, execution budgets, and the remaining V8 coverage gaps. |
| Claim complete Jericho API or Z-machine conformance | **No.** Neither is necessary for this integration. |

This is an evidence-based readiness assessment, not a percentage-complete or
delivery-date estimate. It does not claim that a migrated Cabin Fever server,
browser, voice session, or deployment has been exercised.

## Scope and compatibility policy

The migration may change imports, method calls, return types, checkpoint layout,
and the on-disk save format. **Loading existing Jericho-era Cabin Fever saves is
not a requirement.** Neither is preserving Jericho's nine-field tuple, importing
old Fernz checkpoints, or translating saves between engines. A clean session
boundary is acceptable. These are not reasons to delay the engine swap.

Working saves produced by the *new* integration still matter: Cabin Fever
autosaves every successful turn and resumes sessions after process restart.
That is a functional requirement, independent of backward compatibility. The
review therefore covers the needed behavior without prescribing a file format.

The primary target is the server's `Machine` and its tools. The standalone
`play_jericho.py` utility and installation/deployment assumptions are secondary
migration surfaces. The browser audio, radio, speech services, and companion
model do not directly call Jericho.

Only Fernz's implementation, Cabin Fever's own caller code, and Fernz's existing
tests and recorded public-reference results were inspected. No Jericho or Frotz
implementation source or private native internals were inspected or invoked.
The [clean-room requirement](OVERVIEW.md#mandatory-clean-room-requirement) remains
in force.

## Evidence and current game coverage

The older [compatibility audit](CABIN_FEVER_COMPATIBILITY.md) describes the same
Cabin Fever revision, so its consumer inventory remains useful. Its statements
about limited V5/V8 execution and numbers of available profiles are historical.
The current environment, profiles, and version-specific tests provide the
readiness evidence here.

| Retained builds | Existing execution evidence | Implication for Cabin Fever |
| --- | --- | --- |
| 17 V3, including Zork I–III and LGOP | Complete winning routes; extensive parser detours, losses, randomness, and checkpoint replay. | Strongest starting point. Some games still require startup acknowledgements. LGOP deliberately has no fixed maximum score. |
| 1 V4: Trinity | A 610-command winning route, 318 detours, loss and lifecycle scenarios. | Execution and required queries exist; startup pauses for a key, and victory leaves an active ending menu. |
| 33 V5 | Complete winning routes totaling 7,138 commands and exact-image profiles. | Much broader support than the old audit suggests. Title screens, character input, presentation, and ending menus still need consumer adaptation. |
| 2 V8: Lost Pig and Snack Time | Complete winning routes of 146 and 34 commands, respectively, with query and checkpoint checks. | Reasonable candidates after input and outcome handling is integrated. Both wins leave the VM running at a menu. |
| 4 V8: Afflicted, Anchorhead, Party Foul, Yomomma | Openings, bounded actions, and persistence scenarios; no complete winning routes or story-specific query profiles. | Do not present as fully supported Cabin Fever games yet. Mapping, status, outcomes, and arbitrary play remain gaps. |

Thus **53 of 57 retained builds have measured winning routes and story
profiles**, with different depths of off-route coverage. This is not a 93%
compatibility guarantee. Profiles recognize the exact addressable story image;
another release with the same filename need not have the same capabilities.
LGOP's reference lacks useful game-specific query bindings, so its expectations
also use independently decoded public snapshots and measured output events.

Zork I is particularly well covered: its 396-command route at seed 12 reaches
350 points, with reset and checkpoint replay, 11 branch checkpoints, parser
errors and clarification, combat across seeds, recoverable deaths, and boat
travel. These are relevant to an agent that explores beyond a walkthrough.
They still do not exhaust arbitrary command sequences or all random futures.

The loader accepts V1–V8; execution supports **V3, V4, V5, and V8**. V1, V2, V6,
V7, and Blorb containers must not be advertised as playable merely because a
filename passes Cabin Fever's extension filter. The retained corpus uses the
four implemented execution versions. Detect versions from headers: the file
`zork1.z5` actually contains V3.

Coverage sources: [V3](V3_GAMES.md), [LGOP](LGOP.md), [V4](V4.md),
[V5](V5.md), [V8](V8.md), and [story profiles and outcomes](STORY_QUERIES.md).

## Actual integration surface

Cabin Fever's [server machine][cf-machine] imports `FrotzEnv`, creates it with
a fresh positive seed, and executes synchronous calls through `asyncio.to_thread`.
It retains the last observation, status, current location, current-run routes,
and routes remembered across reloads. The [companion loop][cf-game] disables
parallel tool calls and awaits tool execution in sequence.

| Consumer requirement | Fernz status | Required migration |
| --- | --- | --- |
| Construct, `reset()`, `step()`, `close()` | Implemented, with familiar tuple shapes. | Select `FernzEnv`; convert observation objects to text. Keep operations on one environment serialized. |
| Screen text | `Observation.text` is the plain transcript; `.stream` contains ordered display operations. | Store `.text` where Cabin Fever currently stores strings. |
| Score and moves | Implemented for the 53 profiles; generic V3 fallbacks have limits. | Treat unsupported values as unavailable rather than inventing zeroes. |
| Maximum score | Available for fixed-maximum profiles. LGOP and unprofiled stories raise `NotImplementedError`. | Allow a score without a denominator; gate unsupported games. |
| Location and map keys | Detached `ZObject` with `.num` and full `.name`; later-version player lookup needs a profile. | Preserve current-run mapping with fresh identities and choose a cutover policy for durable remembered routes. |
| Loss, victory, and termination | `game_over()`, `victory()`, and `done` have separate meanings. | Define one episode policy for boot, turns, and restore. |
| Checkpoint and resume | Immutable `GameState`; deterministic restore into a fresh environment is implemented. | Wire new state into autosave/manual-save/resume; no old-save importer. |
| Native RAM-size check | No `frotz_lib`; story metadata and checkpoint validation provide the needed information. | Remove the native call; use story identity and validated `set_state()`. |
| Native RNG replacement on reload | No equivalent immediate reseeding method; `seed()` applies at the next reset. | Decide whether to retain deterministic restore or deliberately implement the consumer's alternate reload policy. |
| Input pauses and execution errors | Exposed directly, rather than hidden by a consumer-specific wrapper. | Handle keys/Enter and recover or retire an invalidated environment. |

Cabin Fever does **not** call `get_valid_actions()`, `get_world_state_hash()`,
`get_dictionary()`, `get_walkthrough()`, `get_world_objects()`, `get_inventory()`,
or `bindings`. Sam proposes commands through its tools; it does not depend on
Jericho's action generator. The paused [world-hash/action-discovery work](WORLD_STATE_HASH.md)
is therefore not on this migration's critical path and need not be resumed.

## Remaining gaps and recommended decisions

### 1. Observation adaptation: required even for Zork

Changing only the import fails at `Machine.screen()`: it calls
`self._observation.strip()`, and a Fernz `Observation` is not a string. The
standalone player similarly expects string operations. Convert at reset and
every step, keeping the stored observation and tool output as text.

Use `.text` for the first integration. It includes both windows in emission
order, preserving clues that might appear in upper-window quotations. It is
not a reconstructed screen: overwritten and cleared text remains in the
transcript. Feeding raw `.stream` into Sam's existing text view would expose
display commands, not render them.

Fernz retains title text and full output that the reference sometimes clips.
Zork's recognized trailing command prompt is omitted from `.text`; other
stories have their own presentation differences. Test readability and clue
retention, not accidental reference clipping. Full terminal rendering is an
optional later feature, not a Zork pilot prerequisite.

The default geometry is 80×25, while many later-version reference routes were
measured at 128×232. Choose the consumer geometry explicitly and test that
configuration; a passing route at reference geometry is not proof of every
layout at the default size. See [observations](OBSERVATIONS.md).

### 2. Episode termination: required even for Zork

Currently, normal Cabin Fever turns trust `step()`'s `done`, while restore uses
`game_over() or victory()`. These must not diverge after migration.

Fernz's `done` means the VM executed `quit`. Its loss/victory methods report
events in the latest response. Zork can report a recoverable death without
quitting; Trinity, LGOP, Lost Pig, Snack Time, and many V5 endings leave a menu
running. Using only Fernz's `step().done` would let Cabin Fever continue where
the reference's outcome-based done flag previously stopped it.

For an initial migration preserving Cabin Fever's episode-on-outcome behavior,
use `env.done or env.game_over() or env.victory()` for supported profiles,
consistently after boot, a turn, and restore. If continued play after a
recoverable death is desired, make that a deliberate product change and test
it separately. Do not infer victory from reaching the maximum score.

An unsupported outcome query is not proof that a game is still in progress.
Either exclude that game or define an explicit reduced-capability mode. Fernz
also intentionally corrects some reference classifications; for example,
Deephome's measured winning ending is recognized as victory. See the version
documents for these exceptions and the terminal Zork move-count difference
(394 in Fernz versus 395 reported by the reference).

### 3. Keys, Enter, and startup sequences: required for the broader catalog

The current [type tool][cf-tools] promises a line of text. `Machine.type_text()`
strips it and returns the screen immediately when it is empty. Fernz exposes
the actual input boundary, including `read_char`; an empty `step("")` can mean
press Enter. At a character request, a longer string supplies only its first
encoded character rather than executing a command line.

The review's raw-reset probe found **11 games initially waiting for a key**:
`anchor.z8`, `curses.z5`, `huntdark.z5`, `library.z5`, `loose.z5`, `partyfoul.z8`,
`sherlock.z5`, `snacktime.z8`, `theatre.z5`, `trinity.z4`, and `tryst205.z5`.
In a direct Trinity
probe, `step("look")` acknowledged the title screen and left the move count at
zero: the intended LOOK command was not executed.

Startup differences also include line-based acknowledgements and choices.
Existing test adapters explicitly advance Hollywood Hijinx, The Lurking Horror,
and Seastalker, and supply Jewel's startup choices. Their success depends on
that orchestration, not an automatic Fernz equivalent of Jericho's reset.

Provide an explicit key/Enter path and make the current input requirement
visible to the adapter/tool. A bounded, per-story startup policy is an
alternative for known title acknowledgements. Do not blindly press Enter until
input becomes a line: menus and substantive choices can also use single keys,
and pauses occur midgame as well as at startup. Preserve text produced across
acknowledgements. The checkpoint exposes the pending input request, but Fernz
does not currently offer a dedicated high-level input-mode property; a small
public convenience API would keep consumer code independent of nested types.

Line input also has deliberate differences: for the pinned Zork I build,
Fernz accepts 99 characters where the measured reference accepts 198 ASCII
characters, and Fernz preserves question marks that the reference substitutes
with spaces. Unsupported input characters can raise `ValueError`. These do not
block ordinary short commands, but test long, punctuated, and non-ASCII tool
inputs and provide a clear input-error response. Do not claim byte-for-byte
parser-input compatibility. See the
[recorded input comparisons](OVERVIEW.md#black-box-reference-tests).

### 4. Catalog and optional metadata: required before unrestricted selection

`Machine.list_games()` currently lists matching files rather than validated
engine capabilities. For the initial release, use an explicit set of tested
story builds. A later version can expose capabilities more generally.

There are two distinct problems:

- **LGOP:** score, moves, location, and outcomes work, but a fixed maximum is
  unavailable by design. The current unconditional `get_max_score()` inside
  `screen()` would raise. Render `Score N` instead of requiring `Score N/M`.
- **Afflicted, Anchorhead, Party Foul, and Yomomma:** no story profiles yet.
  Reset provides empty status; score/move/outcome and later-version location
  queries are unsupported. `_player_location()` already catches `RuntimeError`,
  which includes `NotImplementedError`, so mapping would silently disappear.
  Restore's unconditional score/move queries would still fail. Complete the
  profiles and gameplay validation, or keep these titles outside the supported
  catalog. Do not hide the gap by inventing metadata.

Alternate story releases need the same capability treatment. A filename or a
successful loader call is insufficient to enable all tools.

### 5. Budgets and failure recovery: required handling, especially for larger games

Fernz defaults to 250,000 instructions per reset/step. The existing Afflicted
tests use 2,000,000. This review reproduced a normal `n` command in its
walkthrough prefix exhausting the default budget. Restoring the pre-command
checkpoint and retrying with the test's larger budget succeeded.

Execution failure invalidates Fernz's active episode. Cabin Fever currently
catches a step exception and says the machine locks up "for a moment", then
keeps the same environment. A subsequent Fernz step can fail again until reset
or restoration. A one-instruction failure probe confirmed this behavior and
successful recovery through `set_state()`.

Select bounded budgets for supported games and keep a pre-turn checkpoint if
the desired policy is rollback. On failure, restore it and keep screen, map,
and autosave consistent, or explicitly mark the game unusable and direct the
user to reload. Do not write partial failed execution over the last good
autosave. Merely increasing the budget does not solve all opcode/input errors.
Thread offloading also does not make cancellation of a running VM operation
instantaneous; preserve serialization while a worker finishes.

### 6. New saves and reload behavior: integration work, not a compatibility project

Replace the Jericho-specific codec in [the save layer][cf-saves] with storage for
the current Fernz state and Cabin Fever's own observation, map, and metadata.
Preserve autosave-after-turn, manual slots/comments, restore without issuing
`look`, and resume into a fresh process. Use a new engine/schema identity and
reject incompatible saves clearly. There is no need to preserve old bytes,
tuple offsets, extensions, or Quetzal interoperability for this cutover.

Fernz checkpoints already contain the continuation, RNG, display state, and
outcome flags, and validate the story hash and RAM size. Their current API is
an in-memory representation, not a packaged persistent-session codec. This
storage work may live in Cabin Fever; a general Fernz serialization feature is
not a prerequisite. Keep it a data-only decoder, consistent with Cabin Fever's
existing policy. New-format round trips and failure handling need tests, but
legacy migration tests do not.

The remaining RNG question is **behavioral**, not a file-format issue. Cabin
Fever deliberately changes non-counting RNG trajectories on server reload;
Fernz restores them exactly. `env.seed(new_seed)` does not reseed the active
restored episode. I recommend deterministic restore for the first integration
unless fresh-future reloads are an explicit gameplay requirement. If that
behavior is retained, define and test an immediate public/adapter operation
without weakening deterministic `set_state()`. Existing tests
`test_loading_an_ordinary_rng_state_gives_it_a_fresh_future` and
`test_loading_a_predictable_rng_state_preserves_it` encode the current policy.

### 7. Mapping and remembered context: decide the cutover boundary

Cabin Fever uses `(object_number, name)` as a map key. Fernz preserves full
names, where the reference can return shortened names such as `West House`.
Current-run mapping can use Fernz's keys directly; vehicles can legitimately
be the player's location, as with Zork's magic boat.

Durable [game memories][cf-memories] survive ordinary save reloads and are keyed
by the story signature, which does not change just because the engine changes.
Old maps can therefore mix reference names with new Fernz names even if old
saves are rejected. Start fresh or namespace remembered routes at cutover;
longer term, key identity by story image and object number and treat names as
labels. No old-map converter is required.

Likewise, a clean cutover should not resume an old companion conversation while
silently starting its game over. The [session startup][cf-game] restores the
conversation and then attempts machine resume. Align that boundary with the
new engine's sessions so Sam's remembered progress and the game agree.

### 8. Runtime and deployment: promising, with target validation still needed

Fernz's dependency-free, pure-Python core removes the interpreter's native
build requirement. Its Python 3.11 minimum fits Cabin Fever's Python 3.12
minimum. Use the base library; the optional Textual frontend is unnecessary
for the server.

The reviewed revision prepares 0.0.1; this review did not verify publication to
PyPI. Pin the tested Fernz artifact or commit and verify a clean installation
of the migrated Cabin Fever package without Jericho. A version in package
metadata alone does not establish that the dependency is distributable.

This does not automatically make the whole application native on every OS.
The [core package metadata][cf-package] declares Linux support, the
[launcher][cf-launcher] provisions a Linux guest and C toolchain, and
[browser authentication][cf-auth] imports `fcntl` unconditionally. Other audio
and deployment dependencies remain. Removing Jericho is a useful simplification,
but direct Windows support needs a separate pass. NumPy also remains used by
the Zello audio path, not just the old save codec.

An ad hoc probe successfully handed one Fernz environment between two distinct
worker threads in sequence, restored into a fresh environment, and verified
that a second environment's state did not change. This supports Cabin Fever's
thread-handoff pattern; it is not a concurrent-mutation or load test. Preserve
one operation at a time per environment. On a conventional GIL-enabled Python,
`to_thread` does not supply parallel execution of pure-Python VM work across
sessions.

Measure reset/turn latency, snapshot/storage cost, memory, and event-loop
responsiveness on the actual server and Raspberry Pi 5 deployment, including
multiple active sessions. No target-device benchmark or Jericho-relative
performance claim is made here. Successful desktop correctness tests do not
establish acceptable multi-station latency.

## Gaps that should not block a Zork-first integration

- Old saves, old checkpoint schemas, native tuple compatibility, and
  cross-engine save conversion are explicitly out of scope.
- Missing action discovery, world hashing, cleaned object trees, and other
  unused Jericho APIs are not requirements of the current consumer.
- Full Standard conformance, V6 graphics, Blorb resources, sound playback,
  timed input, and external transcript streams are outside the initial text
  target. Restrict the catalog if a chosen game needs them. Some unsupported
  instructions can still fail on unexplored routes.
- Z-machine sound support is separate from Cabin Fever's radio voice and rain
  audio. Fernz's silent `sound_effect` behavior does not itself disable those
  services. It also does not establish that all sound-dependent story paths
  work; see [sound limitations](SOUNDS.md).
- Exact whitespace, reference-clipped names, and the reference's terminal
  off-by-one move values need not be reproduced. Preserve readable content,
  coherent map identity, and deliberately chosen game semantics.

## Recommended migration sequence and acceptance gates

### Gate A: a supported Zork I pilot

Implement the adapter in Cabin Fever, change its dependency/lockfile, update
the standalone player, and start with the pinned Zork I image. Keep the current
deployment model during this step. Require the following through the actual
`Machine` and tools, not only direct `FernzEnv` calls:

1. Boot and observe show readable text, 0/350 status, correct location, and the
   existing hint-availability reminder. No `Observation` object escapes into
   serialized tool output.
2. Movement, parser errors, inventory, multiple commands, and a clarification
   exchange work; room changes create the expected directed routes and private
   map remarks. Include boat/container location behavior.
3. Manual save, listing, comments, autosave, reboot, and new-process resume
   work with *new* saves. Restore reproduces screen/status/map without advancing
   a move. Bad or wrong-story saves do not corrupt a running session.
4. Recoverable death, terminal death, victory, and restored outcomes follow
   the same documented episode policy. The normal in-game management verbs
   remain intercepted by Cabin Fever's tools.
5. A forced interpreter failure recovers coherently or ends the session
   clearly; another ordinary command does not enter an endless failure loop.
6. Two sessions remain independent across worker handoffs, autosaves, and
   reloads. The browser/radio path completes a real session, and the intended
   host meets the project's agreed latency and memory budgets.

Passing these gates would justify a Zork pilot. More generic Jericho APIs would
not compensate for failing them.

### Gate B: expand to other profiled games

Add explicit character/Enter support, startup orchestration where appropriate,
optional metadata, chosen screen geometry, and per-game budgets. Exercise at
least one representative of each problematic behavior: a V3 startup sequence,
Trinity, a V5 title/menu game, LGOP, and both profiled V8 games. Test midgame
character pauses and ending menus, not only opening screens. Re-run the
corresponding complete routes and relevant detours at the chosen settings.

The other profiled games can then enter a tested catalog incrementally. Winning
routes are evidence of execution, not a substitute for free-form playtesting
with Sam's commands and voice transcription errors.

### Gate C: support the whole retained catalog and broaden deployment

Finish the four remaining V8 profiles and establish full-route and loss/branch
coverage, or explicitly document them as unsupported. Verify the downloaded
ROM identities against the supported set; the downloader follows an upstream
branch rather than an immutable corpus revision. Test the selected deployments
and session counts before removing platform restrictions or changing launch
infrastructure.

## Validation performed for this review

Local checks used Linux x86-64 and CPython 3.12.14. The Fernz development
environment was installed from the frozen lockfile, without installing or
executing Jericho. ROMs were obtained through the repository's normal fixture.

The first focused suite passed **1,131 tests** in 150.93 seconds:

```sh
uv run --no-sync pytest \
  tests/test_env.py tests/test_environment_helpers.py tests/test_state.py \
  tests/test_story_queries.py tests/test_smoke_vectors.py \
  tests/test_zork_vectors.py \
  -m 'not reference' -q --tb=short --durations=5
```

This includes synthetic lifecycle/query/state checks, bounded V3 openings, and
Zork's full route, snapshot replay, detours, combat, and timing/vector checks.
The portable vectors are comparisons to previously recorded public-reference
measurements, not a new live Jericho comparison.

Additional later-version checks were run with:

```sh
uv run --no-sync pytest \
  tests/test_v5_corpus_vectors.py \
  tests/test_v4_vectors.py::test_v4_opening_and_five_commands \
  tests/test_v8_vectors.py::test_v8_opening \
  tests/test_v8_vectors.py::test_v8_winning_route_and_queries \
  -m 'not reference' -q --tb=short --durations=5
```

These **42 tests passed** in 149.12 seconds: all 33 V5 startup cases, Trinity's
opening and five commands, all six V8 openings, and both profiled V8 winning
routes with query/counter checks. The two suites total **1,173 passing tests**.
Elapsed suite times include validation work and are not gameplay latency
benchmarks.

Separate ad hoc probes confirmed:

- All 57 retained files reset successfully at seed 42 and default geometry;
  11 initially awaited character input. Reset is not a complete-play test.
- The four unprofiled V8 games reject the story-specific query surface;
  LGOP rejects only a fixed maximum among the queried capabilities.
- Unadapted `.strip()` fails on `Observation`, and Trinity consumes a supplied
  word as a title-screen key rather than a gameplay command.
- Afflicted's default-budget failure and successful replay at 2,000,000
  instructions after restoration.
- Checkpoint recovery after a deliberately exhausted budget, sequential
  cross-thread use, fresh-environment continuation, and two-environment isolation.

These probes were temporary review checks, not new committed regression tests.
The full multi-platform/manual comprehensive matrix, all 53 winning routes,
fresh-process consumer persistence, and a migrated Cabin Fever end-to-end run
were **not** rerun or implemented for this document. Existing tests establish
the broader recorded coverage; the gates above identify what remains to prove.

## Source map

Fernz implementation: [public environment](../src/fernz/_env.py),
[checkpoint validation](../src/fernz/_state.py),
[execution and input](../src/fernz/_machine.py), and
[exact-image profiles](../src/fernz/_profiles.py).
Consumer regression targets: [save, mapping, RNG, and resume tests][cf-tests].
Further evidence and conventions:
[observations](OBSERVATIONS.md), [RNG](RNG.md),
[testing philosophy](TESTING_PHILOSOPHY.md), and [CI scope](CI.md).

[cf-machine]: https://github.com/afourney/cabin-fever-x86/blob/b4933c8b167635c9ffbd7cd8ffd1307fc0b3d52e/packages/cabin-fever-x86-core/src/cabin_fever_x86_core/server/_machine.py
[cf-saves]: https://github.com/afourney/cabin-fever-x86/blob/b4933c8b167635c9ffbd7cd8ffd1307fc0b3d52e/packages/cabin-fever-x86-core/src/cabin_fever_x86_core/server/_saves.py
[cf-tools]: https://github.com/afourney/cabin-fever-x86/blob/b4933c8b167635c9ffbd7cd8ffd1307fc0b3d52e/packages/cabin-fever-x86-core/src/cabin_fever_x86_core/server/_tools.py
[cf-game]: https://github.com/afourney/cabin-fever-x86/blob/b4933c8b167635c9ffbd7cd8ffd1307fc0b3d52e/packages/cabin-fever-x86-core/src/cabin_fever_x86_core/server/_game.py
[cf-memories]: https://github.com/afourney/cabin-fever-x86/blob/b4933c8b167635c9ffbd7cd8ffd1307fc0b3d52e/packages/cabin-fever-x86-core/src/cabin_fever_x86_core/server/_game_memories.py
[cf-tests]: https://github.com/afourney/cabin-fever-x86/blob/b4933c8b167635c9ffbd7cd8ffd1307fc0b3d52e/packages/cabin-fever-x86-core/tests/test_saves.py
[cf-package]: https://github.com/afourney/cabin-fever-x86/blob/b4933c8b167635c9ffbd7cd8ffd1307fc0b3d52e/packages/cabin-fever-x86-core/pyproject.toml
[cf-launcher]: https://github.com/afourney/cabin-fever-x86/blob/b4933c8b167635c9ffbd7cd8ffd1307fc0b3d52e/packages/cabin-fever-x86/src/cabin_fever_x86/_main.py
[cf-auth]: https://github.com/afourney/cabin-fever-x86/blob/b4933c8b167635c9ffbd7cd8ffd1307fc0b3d52e/packages/cabin-fever-x86-core/src/cabin_fever_x86_core/web_gateway/auth.py
