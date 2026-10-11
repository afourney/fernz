# Raw object inspection

Fernz exposes detached object snapshots through Jericho-style public methods.
This covers initialized **V3 and V5** games. Implementation follows Z-machine
Standard 1.1 [§12](https://inform-fiction.org/zmachine/standards/z1point1/sect12.html),
the [public Jericho API](https://jericho-py.readthedocs.io/en/latest/frotz_env.html),
and black-box comparisons with Jericho 3.3.1. The
[clean-room requirement](OVERVIEW.md#mandatory-clean-room-requirement) applies;
no reference interpreter implementation was inspected.

## Methods

| Method | Result |
| --- | --- |
| `get_object(obj_num)` | One `ZObject`, or `None` for zero, negative, or absent object numbers. Non-integer arguments raise `TypeError`. |
| `get_world_objects(clean=False)` | A Python list in object-number order, including disconnected and invisible objects. Slot zero is an empty `ZObject(0, "")`, so `objects[n]` identifies object `n`. |
| `get_player_object()` | The player identified by the exact story profile, including all 17 retained V3 builds (object 4 for Zork I) and the pinned V5 9:05 build (object 28). |
| `get_player_location()` | A complete `ZObject` for the player's immediate parent, including vehicles. Without a known player, retain the V3 status-location fallback. Zero location returns `None`. |
| `get_inventory()` | A list of the player's immediate children in sibling order. Items inside carried containers remain reachable through their child links. An empty inventory returns `[]`. |

All methods require a successful `reset()` or `set_state()`. They work after
VM quit and neither execute instructions nor invoke output/storage callbacks.
After an execution failure, reset or restore before querying. A query error
does not invalidate or mutate the running environment.

Player and inventory queries require a profile with a known player identity;
unknown identities raise `NotImplementedError`. The Z-machine has no universal
player object. Raw lookup and enumeration do not require a story profile, but
do require the enumerable initial layout described below.

`clean=True` raises `NotImplementedError`. Game-specific cleaning, world hashing,
and action discovery remain deferred; see the
[investigation notes](WORLD_STATE_HASH.md).

## Snapshot fields and navigation

Import `ZObject` from `fernz`. It is a mutable Python dataclass with these fields:

| Field | Meaning |
| --- | --- |
| `num: int` | Stable object number within this story. |
| `name: str` | Complete decoded story short name, which can be empty. |
| `parent`, `sibling`, `child` | Integer object numbers; zero means no link. |
| `attr: list[int]` | 32 V3 or 48 V5 attribute flags, indexed by attribute number, each initially 0 or 1. Meanings are game-defined. |
| `properties: list[int]` | Supplied property numbers in descending order, zero-padded to at least 16 slots for Jericho callers. These are not property values or defaults. More than 16 properties are retained. |

Every query allocates independent records and lists. Editing a field or list
changes only the returned snapshot. Game commands, reset, restore, and changes
to another returned object do not update a saved snapshot. Re-query to observe
the current game state:

```python
player = env.get_player_object()
room = env.get_object(player.parent) if player.parent else None

items = []
number = player.child
while number:
    item = env.get_object(number)
    items.append(item)
    number = item.sibling

player.parent = 0  # Local edit; the live player has not moved.
```

The example assumes a well-founded tree and no game mutation between lookups.
`get_inventory()` checks for sibling cycles and inconsistent parent links and
raises `ExecutionError` rather than looping. Traversing from a single node need
not reach every object because the world can contain disconnected trees.
`get_world_objects()` enumerates the table independently of tree reachability.

The earlier `get_player_location()` returned a frozen `Location(num, name)`.
It now returns the richer, locally mutable `ZObject`; `.num` and `.name` retain
their meanings. `Location` remains importable as a legacy value type, but is no
longer the query's result type. Full VM checkpoints remain immutable `GameState`
values; object snapshots do not change checkpoint semantics.

## Finding the object count

The standard does not store an explicit object count. Its §12 remarks describe
a convention used by inspection tools: initially, the contiguous object entries
end where the earliest property table starts. Fernz walks the original story's
version-specific entries, tracks the earliest property-table address, and requires an exact
entry-aligned boundary within dynamic memory. V3 uses 9-byte entries with a
255-object limit; V5 uses 14-byte entries and word-sized object numbers.

This is a layout convention, not a guarantee of the format. Other legal layouts
can place property tables elsewhere. Ambiguous or unsupported initial layouts
raise `NotImplementedError` for enumeration and nonzero in-range direct lookup;
Fernz does not guess a count by scanning arbitrary RAM. Ordinary VM object
operations remain independent of this optional inspection heuristic.

The count is derived from the immutable original story, not current RAM. Games
may legally relocate property tables during play (§12.4); such changes do not
change enumeration, including after checkpoint restoration or copying. Object
contents and current property pointers are always read from live memory when
creating snapshots. Malformed names or property tables raise execution or
memory errors without modifying the game.

Location queries retain their ability to read a known object directly, including
the existing status-location fallback in stories without an enumerable layout.
Known-player and inventory queries likewise do not need whole-world enumeration.
V5 uses the same inspection contract with its version-specific table layout.

## Measured reference compatibility

Public probes with Jericho 3.3.1 confirm separate mutable snapshots from direct
lookup, player/location queries, inventory, and world enumeration. Changing a
returned parent or property entry does not modify VM state. Previously returned
objects remain unchanged when the player moves, a mailbox opens, or an item is
dropped. Jericho also returns only immediate inventory children.

There are explicit differences:

- Fernz uses Python dataclasses and lists, with no NumPy or ctypes dependency.
  Jericho's `attr` accessor yielded a separate array in the probe; Fernz's list
  is part of the local snapshot and can be edited there. Neither writes to RAM.
- Full story names are preserved. Jericho's public names sometimes omit text,
  such as `small mailbox` becoming `mailbox` or `West of House` becoming
  `West House`. Tests pin all observed Zork name differences.
- In the retained Zork build, Jericho returns `None` for unnamed objects **82**,
  **247**, and **249**, and zero-filled records at their world-list positions.
  Other objects still link to these numbers. Fernz retains these real nodes and
  their fields so callers can traverse the complete raw tree.
- Unsupported profiles/layouts and deferred cleaning are reported explicitly;
  this is not a promise of all-game Jericho compatibility.

Required Linux reference tests compare world fields, player, location, and
inventory at all **397** boundaries of Zork's opening and winning walkthrough.
They exercise direct lookup, local edits, empty inventory, copies, checkpoint
restoration, vehicles, recoverable deaths, and inspection after VM quit.

After the third canyon death, raw reference state differs in the thief's final
position: Fernz has object 114 under object 185, whereas Jericho has it under
object 52. The four affected links are asserted explicitly; all other exposed
fields are still compared. This is a terminal execution-state difference, not
object cleaning or a transformation applied by the inspection API. The existing
final move-count difference is documented in [story queries](STORY_QUERIES.md).

Independent synthetic tests cover field decoding, unnamed/disconnected objects,
nested inventory, property lists longer than 16 entries, the V3 object limit,
out-of-order and relocated property tables, unsupported layouts, malformed
data, lifecycle errors, and the absence of host callback side effects.

The [additional V3 suites](V3_GAMES.md) check every object at every measured
boundary using an independent specification-based decoder of public snapshots.
They also cover unnamed inventory/location nodes, native enumeration limits,
and property lists longer than 16 without truncating Fernz's raw records.


The [V5 suite](V5.md) adds the full 9:05 walkthrough, detours, endings, persistence,
and multiple seeds. Its public reference wrapper returns 32 attributes even for
V5 objects; the additional 16 are verified by independently decoding the public
RAM snapshot. Independent V5 API tests use 300 objects, nested inventory,
attributes 32 and 47, zero slots, large links, malformed chains, unknown profiles,
and checkpoint/copy restoration through loss and VM quit.

Balances and Sherlock also provide profiled player/location/inventory queries.
Their full routes and detours compare complete object records decoded
independently from public reference RAM. Sherlock exposes the same unnamed-child
inventory truncation observed in V3; Fernz keeps the complete raw chain.

For the exact Sherlock image, raw inspection of object 308 preserves an
out-of-order encoded property tail. The compatibility rule applies only to that
object and image. Ordinary malformed order, bounds, and broken tree-link checks
remain enforced, and executable property lookups still validate traversal.
