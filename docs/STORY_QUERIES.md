# Locations, score limits, and outcomes

Fernz exposes `get_player_location()`, `get_max_score()`, `game_over()`, and
`victory()` alongside its existing score and move queries. These methods read
state without executing instructions, emitting text, or consuming randomness.
This work changes Fernz only; Cabin Fever is a reference consumer.

## Location results

`get_player_location()` now returns a locally mutable `ZObject` or `None` when
the selected location number is zero. Import `ZObject` from `fernz`.
The result is detached: subsequent movement or restoration does not change an
earlier result. Names are the complete decoded object short names, including
their original spacing. An empty object name remains an empty string.
The earlier immutable `Location(num, name)` return type has been replaced by the
complete object record, preserving `.num` and `.name`. See
[object inspection](OBJECT_INSPECTION.md) for the remaining fields and raw tree,
direct lookup, player, and inventory methods. `Location` remains importable as a
legacy value type.

For the supported Zork I build, the location is the immediate parent of player
object 4. Public reference queries at all 397 boundaries of the opening and
walkthrough confirm this relationship. A vehicle can therefore be the location:
after command 218, entering the boat returns object 156, `magic boat`, while the
status-line global still contains surrounding room 33, `White Cliffs Beach`.

All 16 retained V3 profiles use the measured player's immediate parent.
For unprofiled V3 stories, Fernz uses the status-line convention in Standard
[§8.2.2](https://inform-fiction.org/zmachine/standards/z1point1/sect08.html):
the first global identifies the object whose short name is displayed. This
fallback works for score and time games; it is not a guarantee that every game
uses that object as the player's immediate container. Later execution versions
need their own location conventions rather than assuming this V3 global layout.

Location queries require successful reset or checkpoint restoration and work
after quit. Malformed object numbers or property/name data raise an execution
or memory error without altering state. The object name is decoded according to
Standard [§12](https://inform-fiction.org/zmachine/standards/z1point1/sect12.html)
and [§3](https://inform-fiction.org/zmachine/standards/z1point1/sect03.html).

Jericho 3.3.1 sometimes returns shortened names. Fernz intentionally keeps the
story names; the required reference tests assert these differences explicitly:

| Object | Fernz | Jericho 3.3.1 |
| --- | --- | --- |
| 180 | `West of House` | `West House` |
| 81 | `North of House` | `North House` |
| 193 | `Living Room` | `Living ` (trailing space) |
| 25 | `Canyon View` | `CanyView` |
| 178 | `Stone Barrow` | `Stone Barrow` |
| 156 | `magic boat` | `magic boat` |

## Story profiles

Score limits and outcome rules are game conventions, outside the Z-machine
instruction set. Private, immutable profiles contain this metadata separately
from opcode execution. All 16 retained V3 builds now have measured profiles; see [V3 games](V3_GAMES.md)
for seeds, player identities, score conventions, and ending differences.
The retained Zork I release 88, serial `840726`, checksum `0xa129` has a maximum
score of 350.

Recognition uses SHA-256 of the original addressable story image, excluding
file padding: `158f1f63b1302591bbce30e1ec23b17909d2a66e39403ed14593a75280b1e7f9`.
The fixture's whole-file hash differs because its 92,160-byte file contains an
84,876-byte logical image. Renaming or changing padding retains the profile;
altering a logical story byte does not, even if the header identity is unchanged.
Other releases must be measured independently before adding their profiles.

`get_max_score()` reads this metadata and is available before reset, after quit,
and after execution failure. Unknown story images raise `NotImplementedError`.
`game_over()` and `victory()` require initialized execution state and a profile;
they raise `RuntimeError` before initialization or after execution failure, and
`NotImplementedError` for initialized but unprofiled stories. Unsupported games
are not guessed to have a zero maximum score or a false outcome.

## Response outcomes and VM termination

The [public Jericho API](https://jericho-py.readthedocs.io/en/latest/frotz_env.html)
describes loss and victory queries. Black-box calls with the pinned reference
show that, for Zork I, these report events in the latest response:

- Jumping from the canyon reports a loss even on the first two falls, when the
  game revives the player and continues accepting commands. An ordinary response
  on the next turn clears the loss report. The third death also halts the VM.
- Reaching 350 points does not report victory. Entering the barrow at the end of
  the walkthrough reports victory and halts the VM.
- Voluntary quit reports neither loss nor victory.

Replacing only the public reference snapshot's narrative with a placeholder
clears its outcome query. Transferring the death or winning narrative into the
opening snapshot changes that query without changing gameplay memory. These
tests establish why RAM or score alone cannot reproduce this public behavior.
No interpreter implementation is inspected.

Fernz independently recognizes the observed complete response lines
`**** You have died ****` and `Inside the Barrow` for this exact story profile,
normalizing whitespace within each line. It does not search arbitrary substrings
of player input or infer victory from score. These are response classifiers, not
universal proofs of a game's internal win/loss state. They classify captured
output only; suppressed output supplies no event to recognize.

After every successful reset or step, Fernz stores two booleans. Queries read
those flags, so no prior transcript is retained or reparsed. A rejected input
leaves them intact. Story restart and Quetzal restore produce a new response and
classify it normally; Quetzal does not save these host-side flags.

`env.done` and `step()`'s done result continue to mean VM quit. This permits play
after a recoverable death. A consumer that chooses to end its episode on a
reported loss or victory can use, for a supported story:

```python
episode_done = env.done or env.game_over() or env.victory()
```

The reference tests keep these distinctions explicit. At the third death Fernz
reports 16 moves and Jericho reports 17, although both print 16; at victory the
equivalent values are 394 and 395. Fernz reads the story's actual counter at quit.

## Checkpoints and validation

`GameState` includes `game_over` and `victory` boolean fields alongside the VM,
display, and RNG state. `get_state()`, `set_state()`, and `copy()` preserve
them, including at input after a recoverable death and after terminal loss,
victory, or quit. Restoration neither executes nor emits an old observation.
The two fields are type-checked before committing changes; unsupported schema
versions are rejected. Only the current checkpoint schema is accepted.
The deterministic RNG and pending-input contracts are unchanged.

Required Linux reference tests compare location numbers, selected complete versus
shortened names, maximum score, and both outcome queries throughout the entire
winning walkthrough. They cover vehicles, recoverable and terminal deaths,
voluntary quit, copies, checkpoint restoration, reset, restart, and Quetzal
save/restore. Synthetic tests cover independent profiles, unsupported builds,
immutable names, malformed locations, schema validation, and failed execution.

Future work includes additional releases and stories, later execution versions,
cleaned world inspection, and native snapshot persistence. Legacy Cabin Fever `.bin`
imports and changes to the Cabin Fever repository are outside this thread.


## V5 profiles

V5 has no standardized status globals. The pinned `905.z5` profile supplies
player 28, maximum score 1, a latest-response victory score, and elapsed minutes
from global 17 minus 545. Its winning and losing response lines are represented
by hashes. [V5 validation](V5.md) compares these queries with the documented
public reference API across the complete route, detours, endings, restarts,
saves, and snapshots. Other unprofiled V5 builds return empty `info` and raise
`NotImplementedError` for unsupported story-specific queries; raw object
inspection is independent of profiles.

The broader V5 milestone adds exact-image profiles for **Balances** and
**Sherlock**, with maximum scores 51 and 100 and player objects 20 and 232.
Their score getters read an unsigned low byte, while move getters read a word.
Complete routes, detours, endings, counter perturbations and persistence are
checked against public executable behavior. Balances' published route wins at
50 points; Sherlock's victory also reports game over. See [V5 phase 3](V5.md#broader-v5-validation-phase-3).


All 33 retained V5 builds now have exact-image profiles. The additional 30 cover
winning routes, per-turn object/player/location/inventory inspection, score and
move widths, maximum scores and response-based outcomes. New profiles give a
recognized win precedence over a restart-menu loss marker. ZTUU uses a byte-wide
move count. See the [V5 route table and reference boundaries](V5.md#complete-retained-v5-winning-routes)
for exact seeds, player numbers, scores, and the intentional Deephome/Murdac
ending differences. Unknown builds still require measured profiles for these
queries; raw object inspection remains independent.

## V8 profiles

The pinned Lost Pig and Snack Time builds now support score, moves, maximum
score, player, location, inventory and outcome queries. Their complete winning
routes compare every query through public reference behavior and portable
hash vectors. Counter locations and widths come from independent public RAM
mutation probes, rather than assuming every later-version game uses the same
globals. Lost Pig's winning menu is reported as victory without also reporting
loss, following the existing Fernz outcome contract. See [V8 coverage](V8.md)
for exact builds, boundaries and the four other V8 stories still without profiles.
