# Cabin Fever compatibility target

Cabin Fever x86 is a concrete consumer target for Fernz. This audit covers its
server, standalone player, persistence layer, and consumer tests at revision
[`b4933c8`](https://github.com/afourney/cabin-fever-x86/tree/b4933c8b167635c9ffbd7cd8ffd1307fc0b3d52e).
Its lockfile selects Jericho 3.3.1. The consumer is MIT-licensed; this document
records its requirements without vendoring its code or game data.

The target is future Cabin Fever integration. The consumer can change its
imports, calls, and save format to use Fernz's public API. Backward compatibility
with existing Cabin Fever `.bin` saves is not required; do not build an importer
or preserve the nine-field tuple layout for that purpose. Existing usage below
identifies capabilities to provide, rather than a requirement for an unchanged
consumer to run against Fernz.

Implementation in this thread is limited to the Fernz repository. Cabin Fever
consumer changes are work for a separate thread; its usage guides Fernz's API
requirements and tests here.

The [mandatory clean-room requirement](OVERVIEW.md#mandatory-clean-room-requirement)
continues to apply. Only Cabin Fever's own caller code was inspected for this
audit. Foreign interpreter implementations, including installed and vendored
copies, remain off limits. Private calls appearing in consumer code identify
migration needs; they do not authorize inspecting or invoking those internals.

## Evidence

All links below identify the audited revision, rather than a moving branch:

- [Server machine](https://github.com/afourney/cabin-fever-x86/blob/b4933c8b167635c9ffbd7cd8ffd1307fc0b3d52e/packages/cabin-fever-x86-core/src/cabin_fever_x86_core/server/_machine.py):
  screen at lines 171-187; boot at 193-221; commands at 244-288; restore at
  347-431; snapshots at 507-525; cleanup at 573-588; location at 606-614.
- [Save format](https://github.com/afourney/cabin-fever-x86/blob/b4933c8b167635c9ffbd7cd8ffd1307fc0b3d52e/packages/cabin-fever-x86-core/src/cabin_fever_x86_core/server/_saves.py):
  format and field definitions at lines 69-139; encoding and decoding at 351-403.
- [Standalone player](https://github.com/afourney/cabin-fever-x86/blob/b4933c8b167635c9ffbd7cd8ffd1307fc0b3d52e/play_jericho.py):
  ROM/save loading at lines 48-80; locations at 92-101; interaction at 120-150.
- [Consumer save tests](https://github.com/afourney/cabin-fever-x86/blob/b4933c8b167635c9ffbd7cd8ffd1307fc0b3d52e/packages/cabin-fever-x86-core/tests/test_saves.py):
  round trips, autosaves, story identity, RNG reload policy, mapping, and command
  interception. The two RNG policy tests are at lines 497-525.

## API coverage

Status here includes the environment helpers introduced in
[PR #12](https://github.com/afourney/fernz/pull/12) and the
[story queries](STORY_QUERIES.md). Fernz still executes V3 only.
Matching a method name is insufficient when the data or behavior differs.

| Consumer call | Audited consumer behavior | Fernz coverage / remaining work |
| --- | --- | --- |
| `FrotzEnv(path, seed=positive_integer)` | The server supplies a fresh seed in `1..2**31-1`, then calls reset. The standalone player omits the seed. | `FernzEnv` accepts the server's seed range. Change the import/class selection in an adapter. Fernz requires explicit reset, which both consumers already perform. Automatic seed policies differ. |
| `reset()` | Return `(observation, info)` at the opening prompt. | Available for V3. Info has score/moves for score-based games and hours/minutes for time-based games. |
| `step(text)` | Return `(observation, reward, done, info)`. The server ignores reward; the standalone player displays it. | Available for V3. Outcome semantics and transcript differences need adaptation, as described below. |
| `close()` | Cleanup on reboot, console exit, and failed console initialization. | Available and idempotent. |
| `get_state()`, `set_state(state)` | Autosave each turn; restore without advancing the game or emitting output. The existing save codec requires a nine-field tuple. | Deterministic checkpoints are available, using immutable named fields. Update the consumer to persist Fernz snapshots in a new format; legacy tuple conversion is out of scope for this integration. |
| `get_score()`, `get_moves()` | Read actual restored values, instead of trusting save-file metadata. | Available for V3 score-based games, including after quit. Time-based games need additional metadata; the final Zork move count has a documented difference. |
| `get_max_score()` | Render `Score current/maximum` whenever info includes a score. | Available for the exact profiled Zork I build: 350. Unknown builds raise `NotImplementedError`. |
| `get_player_location()` | Return an object with integer `.num` and string `.name`, or no supported location. Both form the map key. | Available as detached, locally mutable `ZObject`, using the profiled player's immediate parent or the V3 status fallback. Full names can differ from the reference's shortened names. |
| `game_over()`, `victory()` | Recompute terminal status after restoring; the console also queries it after loading a ROM. | Available for the profiled Zork I build as latest-response flags, preserved in checkpoints. VM quit remains separate; unknown builds raise `NotImplementedError`. |
| `env.frotz_lib.getRAMSize()` | Check the saved RAM length against the loaded story before restoring. | Consumer migration: use `env.story.header.static_memory` or `len(env.get_state().ram)`, plus story identity validation. No native compatibility object is needed. |
| `env.frotz_lib.setRng(a, interval, counter)` | After server restore, replace the RNG state when the saved interval is zero. | Consumer migration: an explicit RNG policy outside deterministic `set_state()` is needed. Deferred `seed()` is not equivalent. |

There are no consumer calls to `copy()` or the `seed()` setter at this revision;
they remain useful library APIs. There are also no calls to an environment
`save()` or `load()` file API: those names belong to Cabin Fever's own `Machine`
and `SaveStore`. The consumer does not call `get_valid_actions()`,
`get_dictionary()`, `get_inventory()`, `get_world_objects()`,
`get_world_state_hash()`, `get_walkthrough()`, or access `bindings`.
These remain separate parts of the broader Jericho compatibility goal.
Raw `get_world_objects()` and `get_inventory()` are now available as described
in [object inspection](OBJECT_INSPECTION.md); this does not change the audited
consumer's calls.

## Behavioral requirements

### Text, status, and locations

Cabin Fever retains the latest observation separately from interpreter state.
Its server strips leading/trailing whitespace for display; the console strips
trailing whitespace and adds its own prompt. Neither removes embedded story
prompts or title text. Fernz currently retains the title, Enter newline, and
story prompt that the tested Jericho observation omits. A presentation adapter
can handle this without changing the interpreter's complete transcript contract.
Restoring must show the saved observation without issuing `look`, which could
advance game state. Fernz checkpoints need no narrative field for this use.

The server stops accepting commands when `step()` returns a true done flag.
After loading, it instead uses `game_over() or victory()`. These paths must agree
under the consumer adapter's policy. Preserve Fernz's distinction between a
halted VM and game-specific outcomes; validate loss and victory separately,
including situations where the game still offers another input prompt.

Location identity must survive reset, copying, and restoration for the same
story build. Display names alone are insufficient: Cabin Fever stores directed
routes using `(object_number, name)` keys and records the exact command that
connected them. Both the current-run map and durable remembered routes depend
on these values. A V3 status location can provide a starting point, but a
general player/location API must account for game conventions and later versions.
Maximum score and outcome detection likewise need documented or independently
measured story metadata; the Z-machine format does not supply universal fields.

### Persistent snapshots

Keep the selected immutable Fernz `GameState` API and add versioned persistence
for that representation. Cabin Fever can adopt a new save format and start new
sessions; importing or converting existing `CFX86SAVE2` `.bin` files is out of
scope. Neither their nine-field tuple layout nor their NumPy buffers constrain
the new format.

New saves need to retain the complete Fernz checkpoint, including RNG state and
the input continuation. Cabin Fever should also persist its observation, room
and map information, comments, and display metadata alongside the checkpoint.
Loading should restore the saved screen without executing a command, then read
current status from the restored environment. Validate the snapshot schema and
story identity, including the story hash already captured by `GameState`;
corrupt or wrong-story saves must leave the running environment unchanged.

The [state bridge](STATE_INTEROP.md) remains test-only for cross-interpreter
functional comparisons. Its measured V3 input pause conversion is still useful
for that independent testing goal; it does not need to become a supported
package API for Cabin Fever. Quetzal story saves retain their separate contract.

### RNG on reload

The server explicitly changes the RNG after a successful snapshot restore when
the saved interval equals zero; otherwise it preserves the counting period and
position. That condition includes explicitly seeded non-counting sequences, so
it must not be interpreted as detecting whether the player selected a seed.
Its standalone player restores the saved RNG unchanged.

Fernz's `get_state()` / `set_state()` must continue to reproduce the captured
trajectory exactly. Support Cabin Fever's alternate reload policy through an
explicit adapter option or separately designed public RNG operation. The
`seed()` setter selects the next reset's seed and cannot implement an immediate
RNG change during restoration. The adapter's operation must not execute an
instruction, consume a move, or reset RAM. Define its effects on later `random 0`
and restart separately, with deterministic tests for both reload policies.

### Lifecycle and game coverage

The server calls synchronous interpreter methods through `asyncio.to_thread`;
sequential operations may run on different worker threads. Support that usage
and independent simultaneous sessions. Serialize operations on one environment;
this audit does not establish a requirement for concurrent mutation of one VM.
Cabin Fever autosaves after boot, every successful command, and restore,
including terminal results, then resumes into a new environment after process
restart. Cheap, detached snapshots and query methods with no side effects are
therefore part of the consumer contract.

The server intercepts save, restore, quit, restart, and related verbs before
calling `step()`, directing users to its own management tools. This is caller
policy and belongs outside Fernz. The standalone player forwards lines directly.
Both use synchronous observation tuples, so no async interpreter API is needed.

The consumer advertises `.z3` through `.z8` and draws games from the same public
collection. Fernz's V1-V8 loader does not establish execution support: current
execution and reference coverage focus on Zork I (V3), even though the fixture
is named `zork1.z5`. Expand execution by header version and test each supported
game profile. Retain Fernz's existing excluded-game policy when selecting ROMs.

## Implementation progress and remaining CI acceptance

1. Implemented: detached locations and exact-image story profiles, initially
   validated for the retained Zork I build. `get_player_location()` and
   `get_max_score()` have no game-specific logic in opcode execution. Required
   reference tests compare room/container numbers and score limits throughout
   the winning walkthrough, including the boat and explicit name differences.
2. Implemented: independently measured `game_over()` and `victory()` behavior,
   with a documented distinction from VM quit and errors for unsupported games.
   Required tests cover ordinary turns, recoverable and terminal loss, victory,
   voluntary quit, snapshots, copies, reset, restart, and Quetzal restoration.
3. Next persistence work: add versioned Fernz snapshot serialization and document
   its public storage contract. Test fresh-process resume, wrong story, malformed
   data, unsupported schema versions, terminal state, and deterministic
   continuation. Consumers can store screen/map metadata alongside new saves;
   updating Cabin Fever's save layer belongs in a separate thread. No old-file
   import tests are required.
4. Add the optional immediate RNG reload policy at the integration boundary,
   while retaining exact default checkpoint restoration. Test both counting and
   non-counting states, a supplied replacement seed, and subsequent reseeding.
5. Add a required Linux integration scenario reproducing the consumer sequence:
   boot Zork, render status, move between rooms, autosave, branch play, reload,
   verify screen/status/map, and continue. Compare public Jericho results where
   applicable and explicitly assert documented transcript/move-count differences.
   Exercise worker-thread handoff and two independent sessions. Expand to later
   story versions as execution support arrives.

Items 3-5 remain planned. CI verifies the environment helpers, story queries,
and deterministic state transfer; it does not yet test persistent consumer
sessions. Future Cabin Fever integration requires separate consumer changes.
Backward compatibility with its current save files is not an acceptance criterion.
