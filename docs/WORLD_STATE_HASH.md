# World-state hash and action discovery investigation

**Status: investigation paused on 2026-10-11.** Neither
`get_world_state_hash()` nor `get_valid_actions()` has been implemented in Fernz.
These notes preserve the findings for a later decision; they are not an
implementation specification or a claim of complete Jericho compatibility.

The public documentation describes the world hash as an MD5 digest of a cleaned
object tree. Black-box measurements also found selected game-specific RAM bytes
that affect it. The exact bytes serialized into MD5 remain unresolved: we have
not independently reproduced the reference digest.

## Clean-room boundary and references

The [mandatory clean-room requirement](OVERVIEW.md#mandatory-clean-room-requirement)
continues to apply. This investigation used public documentation, public API
calls, controlled mutations of public snapshots, and independently constructed
Z-machine stories. Do not inspect Jericho or Frotz implementation source,
installed implementation files, or private/native internals to fill the gaps.

Public references:

- [Jericho environment API](https://jericho-py.readthedocs.io/en/latest/frotz_env.html):
  `get_world_state_hash()`, `get_world_objects(clean=True)`, `get_state()`,
  `set_state()`, and `get_valid_actions()`.
- [Jericho object tree API](https://jericho-py.readthedocs.io/en/latest/object_tree.html):
  public object fields and accessors.
- [Jericho action generator API](https://jericho-py.readthedocs.io/en/latest/template_action_generator.html)
  and [quickstart](https://jericho-py.readthedocs.io/en/latest/tutorial_quick.html).
- Z-machine Standard 1.1
  [object tables](https://inform-fiction.org/zmachine/standards/z1point1/sect12.html)
  and [opcodes](https://inform-fiction.org/zmachine/standards/z1point1/sect15.html).

The documentation pages identify themselves as Jericho 1.3.1; the executable
reference used here was **Jericho 3.3.1**. Documentation claims and measured
behavior are distinguished below. Documentation source links were not used.

## Measurement scope

- Reference environment: Python 3.11 on little-endian Linux, Jericho 3.3.1.
- Story: retained `games/jericho-game-suite/zork1.z5`, whose header identifies
  **V3**, release **88**, serial **840726**, checksum **0xa129**.
- Addressable-image SHA-256:
  `158f1f63b1302591bbce30e1ec23b17909d2a66e39403ed14593a75280b1e7f9`.
  This is the same image recognized by the existing
  [story profile](STORY_QUERIES.md#story-profiles).
- Initial condition: opening prompt after reset with seed **12**.
- Dynamic RAM size: **11,859 bytes**, ending at exclusive address `0x2e53`.

Each controlled mutation or opening-command trial started from the same public
snapshot. Memory was interpreted independently using the Z-machine standard.
Hash and cleaned-object queries preserved the public snapshot in the probes.
These are observations for this exact story and reference version, not rules
for all Z-machine games. They are not yet committed regression tests.

## What affects the hash

Jericho exposes objects with `num`, `name`, `parent`, `sibling`, `child`, `attr`,
and `properties` fields. In the measured V3 reference, the attribute accessor
returns 32 flag values. The property accessor returns a zero-padded list of 16
**property numbers**, not their data values. This distinction helps explain why
many property-value changes leave the hash unchanged.

| Controlled change | Observed hash behavior |
| --- | --- |
| Change an object's short name | Changes; tested by changing player object 4 from `cretin` to `person`. |
| Change which property number exists | Changes; tested by changing player property number 7 to 6. |
| Change an ordinary property value | Can remain unchanged; player property 7 changed from 0 to `0x1234` without changing the hash. Selected exceptions appear below. |
| Move an ordinary object with valid tree links | Changes. |
| Toggle an object attribute | Changes except for the ignored flag described below. |
| Change score or moves only | Unchanged in the probes. |
| Change PC, RNG state, or narrative only | Unchanged in the probes. |
| Change parser input text only | Unchanged in the probe. |

This is a fingerprint of selected game state. It cannot replace Fernz's full
deterministic `GameState`: matching hashes need not imply matching score,
execution position, or future random trajectory. As with any hash, equality is
also not a proof that the inputs are identical.

### Cleaning the object tree

Public documentation says cleaning disconnects noisy objects, giving Zork's
thief as an example. The measured behavior is more specific:

- Flipping each of the 32 attributes separately on player **4**, thief **114**,
  mailbox **160**, and opening room **180** showed that **attribute 3** was
  ignored in all four cases. The other 31 flags affected the hash. The cleaned
  object representation clears attribute 3 in these probes.
- The cleaned representation zeros the thief's parent, sibling, and child
  links and repairs surrounding links to detach it.
- Moving thief 114 to room 180 with a consistently rewired object tree does
  not change the hash. Moving its contained object 115 to room 180 does.
- The thief is not omitted wholesale. Changing its attribute 11 affects the
  hash, for example.

These findings do not establish universal ignored attributes or objects.
Any future Fernz normalization must be scoped to a recognized story profile.

### Selected RAM bytes outside the returned object representation

At the opening prompt, a scan covered **2,845 distinct bytes** spanning all
240 V3 globals and all object-property data ranges. For each byte, the original
snapshot was restored and only the low bit was flipped (`ram[address] ^= 1`).
Exactly two addresses changed the hash:

| Address | Independent interpretation | Opening byte |
| --- | --- | --- |
| `0x1619` (5657) | Low byte of thief object 114's two-byte property 7, which starts at `0x1618`. | `0x05` |
| `0x2298` (8856) | Low byte of global index 19, counting from zero; VM variable `0x23`. The globals table begins at `0x2271`. | `0xff` |

Both changes left the returned cleaned object representation unchanged. The
hash therefore depends on state beyond that representation. The gameplay
meaning of these bytes has not been established.

A further **2,562 bytes**, from the end of the globals table at `0x2451` to the
end of dynamic RAM, were scanned in the same way; none affected the hash.
Together these probes cover **5,407 nonstructural bytes** at one state and one
bit per byte. They do not prove that the two addresses are the only additional
dependencies in every state or for every bit. The addresses apply only to the
identified story image.

## Concrete opening-command examples

Each command below was issued independently from the opening snapshot with
seed 12. The initial reference hash was
`50a82b39d4d82e630a649ff2f9751d06`.

| Command | Reference world hash after command | Move count |
| --- | --- | --- |
| `look` | `50a82b39d4d82e630a649ff2f9751d06` | 1 |
| `inventory` | `50a82b39d4d82e630a649ff2f9751d06` | 1 |
| `wait` | `50a82b39d4d82e630a649ff2f9751d06` | 3 |
| `glorb` | `50a82b39d4d82e630a649ff2f9751d06` | 0 |
| `kick door` | `c6150d102f4778678253da8d80b4a73b` | 1 |
| `open mailbox` | `4025df3d672cc7175c04172c6eddf112` | 1 |
| `north` | `95b0ef3cbfb2d06244b0b561cf6193a5` | 1 |

The opening `get_valid_actions(use_parallel=False)` result was:

```text
['open mailbox', 'north', 'south', 'west']
```

In particular, **`kick door` changes the hash but is absent from the valid-action
list**. Futile object actions were observed setting player attribute 12, and
that attribute affects the hash. Hash inequality alone therefore does not
reproduce action validity. Candidate generation and filtering also affect the
result; this example does not isolate which stage excludes `kick door`.

## Related action-discovery findings

The public contract is a best-guess list of actions that change game state, not
every parser-accepted or informative command. A future implementation could
generate candidates, run each from an isolated checkpoint, compare relevant
effects, and choose representatives for equivalent effects. This remains a
proposal, not implemented behavior.

Additional public reference results:

- After `open mailbox`:
  `['take leaflet', 'close mailbox', 'north', 'south', 'west']`.
- After then taking the leaflet:
  `['close mailbox', 'put down leaflet', 'north', 'put leaflet in mailbox', 'south', 'west']`.

These are observed lists, not a promised ordering contract. Equivalent effects
may have different command strings, such as `drop leaflet` and `put down
leaflet`. Comparisons should account for aliases.

The action query preserved the complete public snapshot in the probes. Ambient
thief movement can occur during otherwise unhelpful commands, so comparing all
RAM bytes would produce false positives. Future speculative execution must
also isolate host callbacks: Fernz's `copy()` currently shares callback
references, so copying alone does not prevent output or storage side effects.

Local action-query probes used `use_parallel=False` and the spaCy English model
`en_core_web_sm==3.8.0`. No dependency, lockfile, or CI configuration was changed.
World-hash and object-tree queries did not require the language model. A future
reference test setup must make any additional dependencies explicit.

Independent inspection of this story's dictionary found 697 entries of seven
bytes each. Bit `0x80` of entry byte 4, counting from zero, matched the public
reference `is_noun` result for every entry. This is an observed convention of
this story, not a Z-machine grammar specification or a portable action
generator. No grammar templates were extracted from reference implementation
files.

### Object-zero execution discrepancy (resolved)

Exploratory command trials also found a separate compatibility issue at the
opening prompt:

- Before the fix, Fernz `step("enter door")` raised
  `ExecutionError: jin at 0x8be7: Invalid V3 object number 0`.
- Jericho responds `You should supply a direction!` and continues.
- An independent synthetic story run through standalone Frotz observed
  `jin 0 0` branching true and `jin 0 1` branching false, with an object-zero
  warning followed by continued execution.

Standard 1.1 defines object zero as meaning nothing, rather than a formal
object. Fernz now applies the measured behavior narrowly to V3 `jin`: a zero
first operand is treated as having parent zero. Other object operations retain
their validation. Synthetic reference tests check both branch polarities;
the Zork regression compares the rejected command, continued play, and complete
converted checkpoints against Jericho. This execution fix does not resume
world hashing or action discovery.

## Open questions when this work resumes

1. Determine the exact digest input serialization through permitted public
   observations if byte-for-byte Jericho hash compatibility is required.
   Straightforward encodings of the returned objects have not reproduced it.
2. Broaden measurements beyond the opening state and low-bit mutations before
   treating the two selected RAM bytes or cleanup rules as complete.
3. Decide whether Fernz needs identical digest strings or its own documented
   state fingerprint with compatible equality behavior. Neither choice has
   been made.
4. Establish action validity and effect deduplication independently from hash
   equality, including incidental changes, score, and game outcomes.
5. Define behavior for unprofiled games. The object-zero `jin` discrepancy
   found during this investigation has been resolved separately, as above.

Implementation and further investigation are paused pending user direction.
