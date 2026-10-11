# V3 gameplay coverage

The retained corpus contains 16 V3 games, identified by their header rather than
filename. `zork1.z5`, `zork2.z5`, and `zork3.z5` all contain V3 stories. All have
complete winning walkthrough comparisons, live on Linux through **public
Jericho 3.3.1 calls** and recorded as hashes for portable replay. We do not
inspect Jericho or Frotz implementation source; the
[clean-room requirement](OVERVIEW.md#mandatory-clean-room-requirement) applies.

## Pinned game conventions

These are the exact retained builds, identified by original addressable-image
SHA-256 in `src/fernz/_profiles.py` and whole-file SHA-256 in the test inventory.
Scores, player identities, and outcome rules are game conventions, not V3
instruction semantics. Other releases require separate measurements.

| ROM stem | Walkthrough seed | Commands | Maximum score | Player object |
| --- | ---: | ---: | ---: | ---: |
| ballyhoo | 0 | 416 | 200 | 211 |
| cutthroat | 10 | 336 | 250 | 184 |
| enchanter | 0 | 265 | 400 | 55 |
| hhgg | 4 | 361 | 400 | 31 |
| hollywood | 0 | 397 | 150 | 50 |
| infidel | 0 | 250 | 400 | 223 |
| lurking | 0 | 294 | 100 | 56 |
| planetfall | 0 | 399 | 80 | 236 |
| plundered | 0 | 189 | 25 | 192 |
| seastalker | 0 | 204 | 100 | 191 |
| sorcerer | 0 | 254 | 400 | 223 |
| spellbrkr | 0 | 412 | 600 | 52 |
| wishbringer | 0 | 184 | 100 | 238 |
| zork1 | 12 | 396 | 350 | 4 |
| zork2 | 0 | 296 | 400 | 4 |
| zork3 | 0 | 273 | 7 | 202 |

The public reference selects recommended seeds and supplies the walkthroughs.
Explicit zero is reproducible for these zero-default games; it must not be
replaced with entropy. See [RNG behavior](RNG.md#host-seeding-and-reset).

Public snapshot perturbations identify the score/move fields. Using zero-based
global indices, Cutthroats reads score 115 and moves 2; Planetfall reads score 1
and moves 225; Wishbringer reads score 136 and moves 135. Other profiles read
score 1 and moves 2. Cutthroats' move query therefore follows its status minutes,
matching the measured reference convention rather than promising an elapsed-turn
counter. Ballyhoo, Cutthroats, Hollywood Hijinx, The Lurking Horror, Planetfall,
Plundered Hearts, Wishbringer, and Zork III expose an unsigned low-byte score;
Seastalker exposes a signed low-byte score. The other scores are signed words.
All move queries read unsigned words. Unsupported time-game profiles still
raise `NotImplementedError` for score/move queries.

Victory and loss are classified from complete normalized response lines, measured
by replacing only the narrative field of a public snapshot and calling the
public outcome methods. New profiles retain SHA-256 fingerprints of those lines,
not narrative excerpts. This is response-event recognition, not an exhaustive
proof of every possible ending. Maximum score alone does not imply victory.

## What each additional game exercises

`tests/v3_cases.py` pins independently authored scenarios and story identities.
For every game besides Zork I, the live and portable suites cover:

- The entire winning route, opening, reward, score/moves, location, player,
  inventory, complete object tree, outcome flags, and canonical VM/RNG state.
- Restoration before every walkthrough command, continuation, and reset.
- Five checkpoints: opening, quarter, half, three-quarters, and 90% of the route.
  Each branches through 65 common commands and 10 game-specific commands,
  followed by `look` and `inventory` unless a loss or victory ends the branch.
  These include unknown verbs, wrong nouns, unresolved pronouns, directions,
  red herrings, parser questions, wait, inventory, and unsuccessful interactions.
- One measured loss sequence and subsequent input, including the replay prompts
  in Infidel and Planetfall and the explicit restart choice in Wishbringer.
  Each branch is replayed from its original snapshot.
- Save, rejected restart, confirmed restart, restore, and continued play, with
  assertions that the actual save/restore callbacks ran.
- Independent copies, detached object-query results, and seeds 1, 42, and 1000.
  Linux also exchanges public snapshots in both directions halfway through the
  walkthrough and continues to the ending.

Hollywood Hijinx has a hedge-maze exploration branch. Zork II tests all eight
Carousel Room exits from the same snapshot, with subsequent look/wait/inventory. Its alternate-seed probes also enter the
Carousel Room and exercise exits. Hollywood Hijinx additionally completes its
full route at seed 7, then resets and repeats it.
Seeds and complete RNG snapshots are checked; restoring a branch must reproduce
its route and output. These cases do not assume exits are fixed or that an
arbitrary walkthrough succeeds under every seed.

Zork I additionally checks ordinary `wait` and `z` advancing three moves,
multiple commands advancing six moves, and unknown verbs advancing none. Boat
branches check its parent room and the player's immediate container after every
turn: the river carries the boat every two moves, can interrupt a wait, and
eventually carries it over the falls. The resulting loss still permits input.

## Explicit reference boundaries

Jericho automatically plays a short startup sequence for Hollywood Hijinx,
The Lurking Horror, and Seastalker. Tests send those exact commands to Fernz
explicitly; the library's reset still stops at the game's first input.
Restart scenarios likewise answer the startup prompts before restoring,
including Plundered Hearts' initial press-return prompt.

Both hosts advertise text-only capabilities for these comparisons. The test
recorder sets only header Flags 1 capability bits through the public snapshot,
including after restart. This avoids screen-specific Seastalker sonar advice.
Presentation normalization removes the exact measured status-display geometry,
the reference's omitted first startup line, and the host input/prompt boundary.
It preserves story text and surrounding newlines. Cutthroats' truncated yes/no
prompt has a separate exact suffix rule. No general whitespace filter is used.

The independent recorder decodes complete V3 objects from public RAM plus the
unchanging original story bytes according to Standard §§3 and 12. It checks
native public fields wherever exposed. Jericho can omit unnamed nodes, stop
inventory traversal at one, return no unnamed location, truncate names, and cap
property lists at 16. Fernz retains complete records and names. The independent
oracle covers these differences and any objects beyond the native enumeration
limit; full RAM hashes still cover every dynamic byte. No decoded names enter
the ZIPs.

Cutthroats, HHGG, Infidel, Planetfall, Zork II, and Zork III execute `quit` on the
winning route, as independently checked with the standalone Frotz executable.
The other new wins remain at input. Fernz's `done` means actual quit; Jericho's
means a reported loss or victory. At these known quits, the native move count
is one larger and its pending-read registers are stale. Tests assert the exact
move difference and compare output, outcomes, and objects, while omitting the
unsupported terminal-state conversion. Zork I retains its corresponding rules.

Cutthroats additionally exposes post-quit changes in the native winning object
snapshot. An independently assembled probe at the ROM's quit instruction,
executed with standalone Frotz, verified the stop-time values. The test helper
asserts each exact link/attribute difference before comparing the remaining
object fields. The interpreter does not execute past quit to imitate these
changes. Lurking Horror's reserved V3 Flags 2 bit 4 is preserved by Fernz and
cleared by the reference; the state bridge normalizes only that reserved bit.

One public-reference trajectory crashes Jericho natively: Hollywood Hijinx,
seed 1, its first ten walkthrough commands, five waits, look, then inventory.
This reproduces using only public environment calls, without object inspection.
The three alternate-seed prefix probes therefore stop at command five, before
activating the model. The main seed-0 winning route, model detours, and maze
coverage remain required. This is a reference limitation, not a passing test
for the excluded sequence.

## Runtime fixes exposed by this corpus

Legacy V3 object-zero queries and writes, out-of-range absent property lookups,
and `print_obj 0` now follow measured executable behavior. The last operation
uses the name pointer immediately before object 1; an empty name uses Jericho's
numeric placeholder (standalone Frotz instead prints nothing). Object rearrangement
can temporarily create a cycle, as Standard §12.5 leaves tree validity to the
story. Seastalker's empty-stack `ret_popped` reads the last local, matching an
independent executable probe. Other stack underflows remain errors.

Dictionary lookup uses inclusive binary-search bounds with exact encoded keys.
This matches the measured lookup of Seastalker's locally unsorted, malformed
terminator entries without modifying the ROM. Synthetic dictionaries pin both
recognized and unrecognized words. Sound requests are silent in the text-only
host, which has no external sound resources (Standard §9).

These changes and the routes do not claim complete V3 conformance, support for
arbitrary releases, screen/sound rendering, or execution of later versions.

## Archives and CI

Each ROM has `tests/vectors/<stem>_vectors.zip`. Zork I retains its existing
archive layout; each additional game has a manifest, walkthrough, five detour
members, scenarios, and seed cases. Archives contain commands, numeric metadata,
and hashes, with **no copyrighted game text, ROM bytes, memory dumps, or saves**.
See [vector generation](VECTORS.md) and [testing philosophy](TESTING_PHILOSOPHY.md).

Three Linux jobs partition the additional games into groups of five. Each runs
live comparisons and checks its archives against fresh public measurements.
The macOS, Windows x64, and Windows ARM Python 3.12 matrix has a core group and
the same three game groups, with no Jericho installation. A shard selects games,
not individual tests, so no game loses its complete route or scenario coverage.

```sh
uv run --no-sync poe test-v3-reference --v3-shard 1/3
uv run --no-sync poe check-vectors --only v3 --v3-shard 1/3
uv run --no-sync poe test-v3-vectors --v3-shard 1/3
uv run --no-sync poe generate-vectors --only hollywood
```
