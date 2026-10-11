# Leather Goddesses of Phobos

The fixture now retains `lgop.z3`: V3 release 160, serial `860521`, SHA-256
`7420823ac2ba15170895e411964f69e527c92beb07a7815a7a02d120eb75983d`.
The complete corpus contains 57 files, including 17 V3 games. Existing local
`games/` directories remain untouched; move an older directory aside to let the
fixture download the complete suite, or add this exact ROM manually.

## Game details

Player object **199** is used for both genders. Entering the men's restroom
(`nw`) selects the male branch with Trent; the ladies' restroom (`ne`) selects
the female branch with Tiffany. Movement, taking/dropping objects, vehicles,
and the laboratory body swap confirm the same player identity. The world has
227 real objects plus the zero sentinel. A player's immediate parent may be a
vehicle, cage, or slab; it can differ from the status room.

`get_score()` reads signed V3 global 1; `get_moves()` reads unsigned global 2.
`step()` rewards are changes in that score. Point awards vary with the RNG;
the story's displayed maximum also changes. The recorded seed-42 win finishes
at 326/326 points after 393 game turns, but **326 is not a fixed maximum**.
`get_max_score()` therefore raises `NotImplementedError` for this build. Other
profile queries work, including player, location, inventory, loss and victory.
Queries never run a scoring command or consume randomness.

The winning run ends at a restart/restore/quit menu, with `victory()` true,
`game_over()` false, and `done` false. Losses also remain at that menu. Complete
normalized response lines identify the observed events; only their hashes are
stored in the profile. A winning response takes precedence over the common
ending-menu loss marker. Subsequent responses classify their own events, as in
other Fernz profiles; these flags do not represent an irreversible story state.

## Independent reference measurements

Jericho 3.3.1 executes this ROM but does not have its game-specific query
binding. Its player lookup returns no object, its walkthrough is empty, and
its score/move/outcome helpers are unavailable as useful expectations. The
LGOP recorder uses **documented public execution and snapshot APIs only**.
No Jericho or Frotz implementation source or private native interfaces are used.
The repository's clean-room requirements apply unchanged.

The recorder obtains score/moves from public snapshot RAM using the V3 status
convention. The independent V3 decoder reads every object from that RAM and the
original static bytes, following Standard 1.1 sections 3 and 12. The known player
number supplies the inventory and location links. Outcome expectations come
from measured output events, independently of Fernz's profile classifier.
The existing measured state bridge compares RAM, frames, PC, RNG and pending
input at each boundary, normalizing only interpreter capabilities and the
previously documented pause representation. Display state is not exposed by
Jericho's snapshot and is not compared through that bridge.

Jericho buffers a final word or prompt outside its public snapshot. Text hashes
therefore cover each complete route or branch, preserving whitespace and words
across input boundaries. The recorder removes only the exact V3 status display
and observed leading command prompts (`>` or ` >`). A final public input flushes
any pending word; only its prefix before the next status display is included.
The flush's game effects are discarded. Before restoring a branch, the recorder
first reaches an ordinary prompt to establish a known frontend buffer. Fernz
removes only its corresponding trailing prompt and associated space for these
comparisons. No general whitespace normalization or missing-text exemption is used.

## Coverage and regeneration

`tests/vectors/lgop_vectors.zip` contains a manifest, bounded smoke route,
complete winning walkthrough, detours, lifecycle cases, and partial routes.
Every record has numeric query expectations and VM/object hashes; text is hashed
across each case. It contains no ROM bytes, narrative text, object names, raw
memory, stacks, or save files. ZIP member hashes are verified before replay.

Coverage includes:

- The 389-input seed-42 winning route, including title and scratch-and-sniff
  acknowledgements. Input count differs from the story's 393-turn counter.
- 75 commands at five checkpoints: 375 branches, each followed by `look` and
  `inventory`. These cover unknown verbs, invalid nouns, parser questions,
  red herrings, movement, waiting, object interactions and losing outcomes.
- Tiffany openings and inventory transfers, a 108-input female route through
  combat and the laboratory body swap, and prefixes at seeds 1 and 1000.
- An explicit opening loss and subsequent menu input.
- Save/restore at three checkpoints, rejected and confirmed restart, and
  continued play. Tests require the actual save and restore handlers to run.
- Restoration and replay before every input, independent copies, complete
  object enumeration and detached query results.

Linux compares fresh reference recordings with Fernz and checks archive
freshness. Portable tests use the ZIP without Jericho or on-disk extraction.
LGOP participates in the existing V3 shards; fast CI plays only its opening
and four inputs. The complete coverage stays in the manual comprehensive suite.

```sh
uv run --no-sync poe generate-vectors --only lgop
uv run --no-sync poe check-vectors --only lgop
uv run --no-sync pytest tests/test_lgop_reference.py -m reference
uv run --no-sync pytest tests/test_lgop_vectors.py -m 'not reference'
uv run --no-sync poe generate-vectors --only storyfiles
```

Reference generation requires the pinned Linux/Python 3.11 reference group.
`tests/routes/lgop.json` preserves the measured command sequence needed to
regenerate the archive, since Jericho supplies no LGOP walkthrough. It adapts
these public gameplay guides, with commands checked through actual execution:

- [Erik Futtrup and Twan Lintermans, 1992](https://ifarchive.org/if-archive/infocom/hints/solutions/lgop.step1)
- [Jacob Gunness, 1991](https://ifarchive.org/if-archive/infocom/hints/solutions/lgop.step3)
- [Public Invisiclues transcription](https://dfabulich.github.io/infocom-hints-html/leather-goddesses-of-phobos.html)

Only functional input commands are retained, not guide prose. The exact route
includes a seed-specific decoded number, a dialogue answer for the headlight,
and repeated dust searching. It is not a universal walkthrough for arbitrary
seeds, other releases, or every branch. The female route is partial, not a
claim of a second complete winning walkthrough.
