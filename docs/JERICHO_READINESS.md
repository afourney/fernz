# Jericho Readiness Report

> Coverage update: all 57 retained builds now have profiles and recorded winning
> routes; LGOP alone has no fixed maximum score. See the [corpus inventory](CORPUS.md)
> and [V8 details](V8.md). The review below describes its pinned implementation
> baseline; its four-game profile/route gap has since been closed.

**Assessment date: 2026-10-11.** This report evaluates Fernz as a replacement for
Jericho in a general customer's application, rather than only in Cabin Fever.
The implementation baseline is Fernz
[`d6e7aa2`](https://github.com/afourney/fernz/tree/d6e7aa2de83004790c599622b7c9c90ddb8caff2),
preparing version 0.0.1. Subsequent readiness-document changes do not alter that
implementation. The repository's executable reference is Jericho **3.3.1**.

## Executive assessment

**Fernz is a credible migration candidate for customers who supply commands,
consume game output, and use checkpoints and common story queries on supported
games. It is not yet a complete replacement for Jericho's agent-development
toolkit.**

That distinction remains true even when the customer accepts reasonable API
changes. Converting an observation to `observation.text` is straightforward
adaptation. Replacing an action-generation pipeline or a world-state hashing
scheme is substantial functionality that Fernz does not currently supply.

The interpreter has progressed well beyond opening-screen demonstrations:
**53 of the 57 retained story builds have measured winning routes and game
profiles**. Several suites also exercise extensive off-route behavior,
checkpoint replay, losses, and randomized scenarios. This supports beginning
real migrations on a defined game set. It does not establish arbitrary-story
compatibility, complete API parity, or readiness for every existing Jericho
customer.

| Customer workload | Readiness judgment after anticipated adaptation |
| --- | --- |
| A text player or LLM companion that supplies its own commands | **Good candidate for a scoped pilot.** Integrate output, input pauses, episode policy, error recovery, and supported-game selection. |
| An agent using player/location/inventory queries and raw objects | **Viable on recognized builds.** Account for object representation and coverage differences; audit every required query. |
| A planner that forks/checkpoints games and supplies its own actions | **Core mechanisms available.** Validate branching throughput, external side effects, and the planner's state-equivalence policy. |
| An RL/search system using valid actions, cleaned objects, world hashes, or action templates | **Not ready as a functional replacement for those dependencies.** These are missing features, not observation-format issues. |
| A benchmark requiring the same seeds, observations, rewards, and termination behavior | **Needs explicit qualification.** Controlled comparisons are feasible, but several deliberate differences change the benchmark contract. |
| A general interpreter for arbitrary Z-machine versions or multimedia stories | **Not ready for that scope.** Execution versions and host services are limited. |

No percentage-complete or calendar estimate is warranted without knowing the
customer's actual API usage, story builds, and deployment targets.

## Assumptions and evaluation standard

The customer is willing to change imports, adapt observations and object
records, and select a new checkpoint/save representation. Exact import names,
native array layouts, legacy save files, and old checkpoint schemas are **not
acceptance requirements**. Existing Jericho-era saves may be retired at cutover.
This report does not count that expected work as missing interpreter capability.

Readiness instead means that the application can retain its required behavior
after a documented migration, with a supported game set and adequate operational
validation. A substitute algorithm that changes the customer's action space,
exploration rewards, or episode boundaries requires explicit agreement; it
cannot be dismissed as a harmless representation change.

The companion [Cabin Fever readiness review](CABIN_FEVER_READINESS.md) applies
this framework to a concrete, relatively narrow consumer. Its unused APIs may
be essential to another customer.

This assessment uses Fernz source and tests, recorded black-box measurements,
and Jericho's public API documentation. The public documentation pages currently
identify themselves as **1.3.1**, despite the repository testing the **3.3.1**
executable. They are useful for the documented surface, not authoritative proof
of every 3.3.1 signature or return value. The customer should inventory its
installed version and callers. No Jericho/Frotz implementation source, private
native internals, or documentation source links were inspected. The
[clean-room boundary](OVERVIEW.md#mandatory-clean-room-requirement) applies to
any work proposed below.

## Capability inventory

Status is based on the implemented [environment](../src/fernz/_env.py) and
[package exports](../src/fernz/__init__.py). Method-name similarity alone does
not establish identical behavior.

### Available building blocks

| Customer dependency | Fernz provision | Migration consideration |
| --- | --- | --- |
| Environment construction and cleanup | `FernzEnv(path, seed=...)`, `close()` | Explicit `reset()` starts execution. Constructor options also supply geometry and host callbacks. |
| Reset and one-command execution | `reset()` and `step()` | Familiar tuple shapes, with `Observation` as the first element and an explicit instruction budget. |
| Plain or structured output | `.text` and `.stream` on `Observation` | Select the appropriate projection; neither implies byte-identical reference output. |
| Reward and info | Score delta plus an info dictionary | Reward is an integer; available counters depend on the story. Do not assume all dictionaries have score/moves. |
| Fork and rewind | `copy()`, `get_state()`, `set_state()` | Independent VM state and deterministic replay; host callbacks and their external effects remain outside the checkpoint. |
| Seed control | Constructor seed and deferred `seed()` | Select explicit seeds. Automatic and zero-seed policies differ from reference defaults. |
| Score, moves, maximum | `get_score()`, `get_moves()`, `get_max_score()` | Exact-image profiles provide game conventions. Unknown or unavailable values raise explicitly. |
| Player, location, inventory | `get_player_object()`, `get_player_location()`, `get_inventory()` | Known player profiles are required except for the V3 location fallback. Locations can be vehicles. |
| Object lookup and raw enumeration | `get_object()`, `get_world_objects(clean=False)` | Detached Python records; enumeration assumes a supported object-table layout. |
| Loss and victory | `game_over()`, `victory()` | Latest-response classifiers for profiled builds, separate from VM termination. |
| VM termination | `done` and the third `step()` result | True on VM `quit`; not a universal episode-over signal. |
| In-game save/restore | Quetzal through host storage callbacks | Available for supported execution versions. Host checkpoints remain the mechanism for deterministic rewind. |

Jericho's documented `load(story_file, seed=...)` has no same-object equivalent
in Fernz. Creating a new `FernzEnv` is a small adapter change for ordinary
clients; applications that retain references to the old environment should
centralize that replacement.

### Missing higher-level functionality

| Customer dependency | Current status | Consequence |
| --- | --- | --- |
| `get_valid_actions()` | Absent | No Fernz-supplied admissible-action set for search, action masking, or policy input. |
| `get_world_state_hash()` | Absent | No compatible world-state key for visited-state caches, novelty rewards, or deduplication. |
| `get_world_objects(clean=True)` | Explicit `NotImplementedError` | Raw enumeration does not reproduce the reference's game-specific noise filtering. |
| `get_dictionary()` / `DictionaryWord` | No equivalent public API/export | Parser execution works, but customer-facing vocabulary and word classifications are missing. |
| `bindings` / `act_gen` / `TemplateActionGenerator` | No equivalent public surface | No packaged reference-compatible grammar templates, action generator, or binding dictionary. |
| `get_walkthrough()` and recommended walkthrough-seed lookup | Absent from the public runtime | Tests have route evidence; the installed library does not offer a walkthrough service. |
| Jericho utility/definition imports | No equivalent compatibility modules | Callers of tokenization, object extraction, parser-response recognition, subtree helpers, or action constants must provide replacements or remove those dependencies. |
| `frotz_lib` and native/private access | No compatibility facade | Migrate each use to an appropriate public contract; native pointers and internal calls are not a supported target. |

The public Jericho references for this inventory are
[environment methods][jericho-env], [dictionary records][jericho-dictionary],
[action generation][jericho-actions], [object records][jericho-objects],
[utilities][jericho-util], and [definitions][jericho-defines]. Utility coverage
is an import-audit requirement, not a claim that every helper deserves a Fernz
implementation. In particular, tokenization or parser-recognition changes can
alter a learning pipeline even if they are easy to replace mechanically.

## Why the missing agent features matter

### Action discovery is a separate capability from executing actions

Fernz can execute a customer-supplied command and rewind to try another. It
does not generate the command candidates, identify their objects and grammar,
filter meaningful effects, or choose representatives for equivalent actions.
Customers who already own those mechanisms can use the existing execution
core. Customers who obtain them from Jericho cannot simply redirect the calls.

The paused [action/hash investigation](WORLD_STATE_HASH.md) illustrates the
gap: at the measured Zork opening, `kick door` changed the reference world hash
but did not appear in its valid-action list. A changed hash is therefore not
sufficient to reconstruct the action oracle. Parser acceptance, useful effects,
candidate coverage, ambient changes, and effect deduplication are distinct
questions. No new implementation or completion commitment is implied by this
report; the investigation remains paused.

### Checkpoint equality is not world-state equivalence

A checkpoint includes counters, execution continuation, input, randomness, and
display state. Two checkpoints can differ while representing the same useful
exploration state. Hashing all checkpoint bytes is not a substitute for a
cleaned world hash: it can split states on move counters or RNG progress and
change the behavior of a planner or novelty reward.

Conversely, hashing only raw objects can miss relevant state. The existing
black-box investigation found reference-hash dependencies in selected RAM
bytes beyond the returned object records. Its exact serialization remains
unresolved. A customer-owned fingerprint is possible, but its equivalence
rules and impact must be validated as a new algorithm; identical digest strings
and identical equivalence behavior are separate requirements.

### Branching must isolate external effects

`copy()` forks memory, frames, pending input, RNG, and outcome flags. It retains
the same output/save/restore callback references. A speculative command can
therefore still print to the live output destination or write to shared storage.
Checkpoint restoration does not roll those effects back.

Use isolated callbacks/storage for speculative environments and test that
discarded branches leave no external effects. There is no public callback
setter: a fresh environment with isolated handlers followed by `set_state()`
is one available design. Test its cost before choosing it for high-throughput
planning. Same-environment concurrent mutation is not an established contract.

## Anticipated differences and their practical impact

### Observations: an expected adaptation, not a readiness defect

For a customer that wants plain text, the basic conversion is small:

```python
from fernz import FernzEnv

env = FernzEnv("games/zork1.z5", seed=12)
try:
    observation, info = env.reset()
    opening_text = observation.text
    observation, reward, vm_done, info = env.step("open mailbox")
    response_text = observation.text
finally:
    env.close()
```

Perform the conversion at the application's environment boundary, before
string operations, JSON encoding, prompt construction, or replay-buffer storage.
Keep the richer observation if the application wants rendering information.

`.text` contains plain text from both windows in emission order, including
upper-window clues. It is a transcript, not the final screen after clears and
overwrites. `.stream` preserves display operations; a renderer must interpret
them and the documented literal-text escaping. Blindly removing angle-bracket
expressions is unsafe for story text. A checkpoint does not contain rendered
screen cells, so a graphical frontend owns its screen restoration.

Title lines, prompts, whitespace, and reference output clipping differ. These
are acceptable for a readable player under the stated assumptions, but matter
to exact transcript tests and learned policies that consume particular tokens.
Use narrowly justified comparison rules and preserve clues rather than broadly
normalizing away differences. See [the observation contract](OBSERVATIONS.md).

### Input boundaries and startup

Fernz returns at real input boundaries. Some reference resets advance title
acknowledgements or startup choices; existing Fernz test adapters explicitly
perform those actions. Of the 57 retained stories, an ad hoc seed-42 raw-reset
probe found 11 initially waiting for character input. Other startups use line
input for acknowledgements or choices.

At a character request, `step("")` supplies Enter and a longer string supplies
its first encoded character. An application that sends `look` without noticing
a title pause may consume only the `l`. A loop that refuses empty input cannot
deliver Enter. Support single keys and acknowledgements at startup and during
play, preserve their output, and avoid automatically answering substantive
choices. Pending input is present in `GameState`; a dedicated public input-mode
property would make this integration cleaner but is not implemented.

Known parser-input differences also remain: the pinned Zork build accepts 99
characters in Fernz versus 198 ASCII characters in the measured reference, and
Fernz preserves question marks that the reference replaces with spaces.
Unsupported input characters can raise `ValueError`. Validate the customer's
actual generated commands, especially long lines and non-ASCII input.

### Termination, scores, and benchmark meaning

Fernz distinguishes a halted VM from a reported loss or victory. A recoverable
death can set `game_over()` while the VM still accepts commands. A winning
ending menu can set `victory()` while `done` remains false. Outcome flags
describe the latest response, not an irreversible game-state proof.

For a profiled game, a customer that ends episodes at any reported outcome can
use `env.done or env.game_over() or env.victory()`. A customer that allows
continuation after recoverable death needs a different policy. Apply the chosen
policy consistently after reset, step, copying, and restore. Unknown-profile
outcomes raise rather than silently meaning false. Maximum score is not a
victory detector.

Scores, moves, and maxima are game-specific conventions. The profiles cover
the measured widths, offsets, and response-dependent scores. LGOP has no fixed
maximum, so `get_max_score()` raises even though its other profile queries work.
An unprofiled V4/V5/V8 story returns empty info; unprofiled V3 time games expose
hours/minutes rather than generic score/moves. Move counters are not necessarily
the number of host commands.

Some differences are corrections or deliberate policies: Zork's winning move
count is 394 instead of the reference's 395; Fernz recognizes Deephome's printed
win where the reference reports loss; several winning menus are not classified
as losses. These are reasonable player-facing behaviors. For research, version
the environment contract and rebaseline affected metrics instead of claiming
that old and new results are automatically interchangeable.

### Randomness and replay

Explicit seeds and full checkpoints support reproducible trajectories on the
validated paths. Do not assume default seeding matches Jericho: Fernz's
`seed=None` selects entropy, while the reference can select a game's recommended
walkthrough seed. Explicit zero is a deterministic zero seed in Fernz; the
reference's `seed(0)` may select a different recommended seed, such as 12 for
the retained Zork I build.

`seed(value)` applies at the next reset, not immediately to a running episode.
Checkpoint restore recovers the active generator and host policy without
drawing randomness. `copy()` also retains any pending next-reset seed; the
checkpoint itself does not retain that separate pending choice. The documented
copy-before-reset behavior differs from the measured reference in this corner
case. Ordinary unseeded trajectories are not promised to match other engines
or arbitrary future Python releases. Record explicit seeds and engine/runtime
versions for experiments. See [RNG contracts](RNG.md).

### Object records and inspection

Fernz returns detached dataclasses and ordinary lists rather than native
structures. It preserves full names, unnamed/disconnected objects, all 48
later-version attributes, and property lists beyond 16 entries. Some reference
wrappers shorten names, omit unnamed nodes, or expose only a prefix of a world
table. Editing the returned Fernz object does not change the VM; re-query for
fresh state. Inventory contains immediate children, not a flattened bag.

These differences are expected representation work, but can change an agent's
features and action candidates. Do not truncate new data merely to reproduce
an old wrapper limit unless the experiment requires that projection. Object
property lists contain property **numbers**, not their values. Raw world
enumeration also depends on an initial-layout convention; some otherwise legal
stories can execute without supporting it. Names are display labels, so durable
identities should include the story build and object number. See
[object inspection](OBJECT_INSPECTION.md).

## Game and interpreter coverage

| Scope | Current evidence | Remaining qualification |
| --- | --- | --- |
| 17 retained V3 builds | Complete winning routes, with extensive detours, losses, and replay. | Exact builds; arbitrary play and every seed are not exhausted. LGOP uses independent query expectations where reference bindings are unavailable. |
| Trinity, the retained V4 build | 610-command route plus detours, loss, and lifecycle checks. | Startup key handling and outcome-menu policy need adaptation. |
| All 33 retained V5 builds | 7,138 winning-route commands in total, with exact-image profiles and query checks. | Alternative endings and off-route coverage vary; later-version geometry and character pauses matter. |
| Lost Pig and Snack Time, V8 | Complete 146- and 34-command winning routes with profiles. | Winning menus remain active; loss-path coverage is more limited. |
| Afflicted, Anchorhead, Party Foul, Yomomma, V8 | Openings and bounded gameplay/persistence. | No full winning routes or player/score/outcome profiles; not equivalent to fully supported agent environments. |
| V1, V2, V6, V7 | Loading/inspection and synthetic format coverage. | Execution unavailable. |

The 53-of-57 figure counts measured builds; it is not a compatibility percentage
for arbitrary customer ROMs. Profiles use the original addressable-image hash,
so another release with the same name needs separate validation. A `.z5`
extension does not determine the version: the retained Zork I image is V3.

Additional limits include Blorb containers, sound playback/completion callbacks,
timed input, external transcript/command-file streams, and in-game undo.
`save_undo`/`restore_undo` explicitly report unavailability; host checkpoints
do not make the story's UNDO command implemented. Sound instructions are silent;
timed requests can raise unsupported-operation errors. Correct capability flags
and working fallback paths do not prove that every story tolerates unavailable
services. Full conformance is not claimed.

Tests for many later-version routes use 128×232 geometry, whereas the library
defaults to 80×25. Validate the chosen customer geometry, including upper-window
clues and character pauses. Existing tests include narrow, explicit exceptions
for reference clipping, limited inspection records, and terminal execution
differences; those qualifications must travel with claims of compatibility.
Sources: [V3](V3_GAMES.md), [V4](V4.md), [V5](V5.md), [V8](V8.md),
[LGOP](LGOP.md), [sound](SOUNDS.md), and [observations](OBSERVATIONS.md).

## Checkpoints, persistence, and lifecycle

The immutable `GameState` captures the VM continuation, dynamic RAM, frames,
pending input, randomness, logical display state, and outcome flags. It can be
restored into a fresh environment for the same story without issuing a command
or replaying old output. Validation rejects wrong-story and malformed states
before replacing live state. These are useful foundations for planning and
session resume; conversion to Jericho's tuple is unnecessary for this migration.

A customer's persistence layer still needs a data-only representation, schema
identity, its own observation/UI metadata, and a tested fresh-process resume
path. Fernz does not currently package a general persistent-session codec.
This is bounded integration work under the accepted new-format policy, not a
requirement to preserve old formats. Customers that only keep states in memory
do not need to build disk persistence at all.

Story-level SAVE/RESTORE is a separate implemented feature. Library customers
provide synchronous Quetzal callbacks; absent handlers report save/restore
failure rather than choosing a filesystem destination. Quetzal restore retains
the receiving RNG policy, unlike deterministic host checkpoint restore. Do not
use the two interchangeably for experiment rewind. Callback exceptions can also
fail execution. See [save/restore contracts](SAVE_RESTORE.md).

At review time, the default instruction budget was 250,000 per reset/step. The
[Lost Pig fix](ISSUE58.md) raises it to 1,000,000 without revalidating all
Afflicted paths. An existing Afflicted
case exceeds it during ordinary play and succeeds at the tests' 2,000,000 budget
after checkpoint restoration. Following an execution failure, the environment
must be reset or restored before reuse. Catching an exception and calling
`step()` again is not recovery. Preserve a pre-turn checkpoint when rollback is
required, and keep external UI, storage, and agent state coherent with that
rollback. Unsupported queries and rejected inputs should not all be treated
as VM failure; handle the documented exception contracts.

## Performance, packaging, and operational readiness

The base library is pure Python, requires Python 3.11+, and declares no runtime
dependencies. Textual is optional. A pure-Python wheel and source distribution
were built and passed the repository's isolated installation checks during
this review. That verifies the local package, not publication to PyPI or a
long-term API-stability commitment. Pin the validated version/artifact.

The migration can remove Jericho's interpreter build dependency from the
customer's runtime. It does not remove unrelated platform constraints in the
application, and it does not establish a performance comparison with the
native reference. The existing CI matrix includes Linux, macOS, Windows x64,
and Windows ARM checks; this review did not rerun that entire matrix.

For interactive play, measure startup and turn latency on the target host. For
search/RL, additionally measure steps per second, snapshot/copy cost, full-world
query allocation cost, memory per branch, and multiple-worker throughput.
Passing a walkthrough is not evidence of competitive training throughput.
Conventional GIL-enabled Python threads do not execute pure-Python VM work in
parallel; process isolation or other deployment choices need customer-specific
measurement. Sequential worker-thread handoff was probed successfully, but
same-environment concurrent mutation is not validated.

The current corpus tests follow an upstream download URL and then verify
expected game identities. Qualify the actual customer ROM set and retain its
hashes. Distribution checks exclude game ROMs from Fernz's packages; replacing
the interpreter does not supply the customer's game assets or their permissions.

## Customer qualification and migration plan

### 1. Inventory the real contract

Record the customer's Jericho version, exact ROM hashes, Python/platform
targets, and every environment, utility, binding, and native call. Identify
whether observations are merely displayed, fed to a learned policy, or compared
exactly; whether action candidates are customer-owned; and whether world hashes
define novelty, caching, or reward. Specify episode, seed, and unsupported-game
policies before calling the migration equivalent.

### 2. Separate three work categories

| Category | Examples | Treatment |
| --- | --- | --- |
| Expected adaptation | `.text`, dataclass/list objects, new environment instead of `load()`, new checkpoint representation. | Implement at the customer boundary; do not count as missing engine behavior. |
| Semantic qualification | Seeds, character pauses, termination, object completeness, presentation, unavailable metadata. | Agree on intended behavior and test observable consequences. |
| Missing capability | Action discovery, cleaned hashes, dictionary/bindings/templates, unsupported versions/services. | Implement independently, substitute an explicitly accepted approach, or narrow the supported workload. |

### 3. Prove a representative pilot

Use a profiled build and run the actual application through boot, ordinary
commands, invalid commands, ambiguity, movement/inventory, an ending, and
checkpoint/copy replay. Add a character-input story if the target set includes
one. Include callback isolation for planners, fresh-process resume for persistent
clients, and failure recovery for all clients. Test the chosen geometry and
limits rather than borrowing only the reference test settings.

### 4. Gate rollout on the customer's dependencies

For a command-driven application, the gate is a passing adapted workflow over
its supported games, reliable lifecycle behavior, and acceptable target-host
performance. It need not wait for world hashing or action generation it never
uses. For an action-oracle or world-hash customer, those absent capabilities
remain release blockers until supplied or deliberately removed from the design.

For research, compare action distributions, observation projections, reward and
termination events, and seeded trajectories. Rebaseline results where contracts
change. Full parity is a stronger claim than successful play and needs its own
evidence. If a rollout retains a Jericho fallback, start distinct engine sessions;
do not imply checkpoints can be moved between them automatically.

## Evidence and validation limits

The immediately preceding Cabin Fever review ran **1,173 passing tests** on the
same Fernz implementation: 1,131 environment/state/query/V3-smoke/Zork-vector
tests and 42 later-version startup/route tests. That included the complete Zork
route and both profiled V8 winning routes. It also probed all 57 raw resets,
query availability, character input, instruction-budget recovery, independent
environments, and sequential worker-thread handoff. These results are reused
here; they were not rerun or counted as new executions.

For the broader Jericho review, additional raw-object, observation, RNG, and
restart checks were run:

```sh
uv run --no-sync pytest \
  tests/test_object_queries.py tests/test_observations.py \
  tests/test_random.py tests/test_restart.py -q --tb=short
uv run --no-sync poe build-check
```

The additional selection passed **114 tests**, with one ROM-marked test
deselected by the normal default marker filter. The package build and isolated
installation checks also passed. All local runs used Linux x86-64 and CPython
3.12.14. The public environment/export inventory was checked directly against
Fernz; missing APIs above are not inferred just from an old progress document.

No fresh live Jericho comparison, complete 53-route rerun, target-device
benchmark, real customer port, or action/hash implementation was performed for
this report. Existing portable vectors encode recorded public-reference
measurements and explicit exceptions; they do not prove complete behavioral
equivalence. Some older design documents describe earlier version milestones;
this assessment uses the current code and later version-specific coverage.

**Recommended decision:** begin migrations for command-driven customers with a
defined supported-game set and accepted adaptations. Treat general Jericho
agent-toolkit replacement as unfinished work, with action discovery and
world-state equivalence among the largest remaining functional gaps.

[jericho-env]: https://jericho-py.readthedocs.io/en/latest/frotz_env.html
[jericho-dictionary]: https://jericho-py.readthedocs.io/en/latest/dictionary.html
[jericho-actions]: https://jericho-py.readthedocs.io/en/latest/template_action_generator.html
[jericho-objects]: https://jericho-py.readthedocs.io/en/latest/object_tree.html
[jericho-util]: https://jericho-py.readthedocs.io/en/latest/util.html
[jericho-defines]: https://jericho-py.readthedocs.io/en/latest/defines.html
