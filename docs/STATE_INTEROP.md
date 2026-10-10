# Test-only state interchange

`tests/state_bridge.py` converts checkpoints between Fernz and **Jericho 3.3.1
on little-endian Linux**, at V3 line-input boundaries. This lets a test play a
prefix in one interpreter, transfer its live state, and continue in the other
without replaying commands. The adapter is test infrastructure, not an installed
Fernz API or a portable saved-game format.

The measurements below come from **public `get_state()` / `set_state()` calls
and independently hand-assembled stories**. No interpreter implementation
source, reflection, or private/native APIs are used. The project's
[clean-room requirements](OVERVIEW.md#mandatory-clean-room-requirement)
apply to this work as well. The Z-machine Standard describes
[routine state](https://inform-fiction.org/zmachine/standards/z1point1/sect06.html),
[instruction operands](https://inform-fiction.org/zmachine/standards/z1point1/sect04.html),
and [header ownership](https://inform-fiction.org/zmachine/standards/z1point1/sect11.html);
the external tuple encoding is an observed property of the pinned reference.

## Using the adapter

Both environments must load the exact same story image, use the same explicit
positive host seed, and keep screen output enabled. Capture the template after
a fresh reference reset. It supplies the destination's interpreter-owned header
settings; it does not supply gameplay state to later conversions.

```python
from fernz import FernzEnv
from jericho import FrotzEnv
from tests.state_bridge import StateBridge

path = "games/jericho-game-suite/zork1.z5"  # This fixture is V3.
reference = FrotzEnv(path, seed=12)
env = FernzEnv(path, seed=12)
try:
    reference.reset()
    bridge = StateBridge(env.story, reference.get_state(), seed=12)

    reference.step("open mailbox")
    reference.step("take leaflet")
    env.set_state(bridge.from_jericho(reference.get_state()))
    env.step("read leaflet")

    reference.set_state(bridge.to_jericho(env.get_state()))
    reference.step("inventory")
finally:
    env.close()
    reference.close()
```

Conversion executes no story instructions and draws no random numbers. Import
can initialize a fresh Fernz environment before `reset()`. The Jericho recipient
must already be initialized with the same story and host seed. Its prior
observation is set to `b"Observation not available"`; the next `step()` returns
the newly generated observation normally.

## Measured public snapshot layout

The pinned reference returns a nine-entry tuple:

| Index | Value | Conversion |
| --- | --- | --- |
| 0 | Dynamic RAM, `uint8` array | Copy bytes; adapt only destination-owned header settings. |
| 1 | Stack, `uint8` array of 2,048 bytes | Decode 1,024 little-endian 16-bit words into call frames. |
| 2 | PC | Translate the pending read boundary as described below. |
| 3, 4 | Stack and frame pointers | Indices into the word array; stack grows toward lower indices. |
| 5 | Frame count | Number of called routines, excluding the initial execution context. |
| 6 | Current opcode | Must be `0xe4`, the measured V3 line-input boundary. |
| 7 | RNG tuple | Translate the active state, counting period, and counter. |
| 8 | Narrative bytes | Ignore on import; supply the placeholder on export. |

RAM length must match the story's static-memory boundary. For the pinned Zork I
image this is 11,859 bytes. Snapshots do not embed the whole ROM or a full story
hash: checking array sizes and header fields cannot establish ROM identity.
Tests pin the ROM hash and provide its `Story` explicitly.

### Frames and return addresses

The empty stack has `sp = fp = 1024`. Each called routine has four header words
beginning at `fp`:

| Offset from `fp` | Observed value |
| --- | --- |
| 0 | `(local_count << 8) \| argument_count` |
| 1 | Parent frame pointer minus one. |
| 2 | Low nine bits of the caller's store-byte address. |
| 3 | Remaining high bits of that address. |

Local 1 is at `fp - 1`, followed downward by subsequent locals. Evaluation
values continue downward to `sp`; Fernz stores them in the opposite order,
with the top value last. Walking to a parent sets its `sp` to the child's
`fp + 4` and its `fp` to the saved parent word plus one. Following the recorded
number of frames must reach the initial context at `fp = 1024`.

Fernz resumes a caller after its store byte and records the store destination
separately. Import reads that destination from live story memory and advances
the saved address by one. Export subtracts one and verifies the store byte
still agrees. Tests vary local and argument counts independently, retain stack
sentinels in each frame, return to both local and global destinations, and
exercise return addresses above 64 KiB.

### Suspended input

At a public input boundary, the reference PC points just after the `sread`
opcode byte, before its operand types. Fernz has already decoded the whole
instruction and resolved its text/parse operands. A variable-zero operand
therefore remains on the reference stack but has already been popped in Fernz.

Fernz deliberately keeps its current boundary, as recorded in the
[execution design](OVERVIEW.md#execution-foundation). The Standard defines
`read` behavior without prescribing a host API's suspension point; either
convention can be correct. Interchange must preserve the pending read and
account for operand evaluation so that input and stack pops occur exactly once.

Import decodes the pending instruction and resolves its operands left to right,
performing any pops once. Export uses the saved input instruction address and
pushes those operands back in reverse order, so the reference resolves them
once on its next step. The adapter verifies that re-resolving the operands
reproduces Fernz's input request and remaining stack. Synthetic stories cover
constant, local, global, and stack operands.

### Memory, randomness, and output

Conversion preserves story RAM except for the V3 capability bits `0x70` in
header byte 1 and the advertised Standard version at `0x32..0x33`. These are
replaced with the receiving interpreter's settings. Flags 2 and all other
gameplay bytes are retained; protected header fields are validated on import.

The reference exposes a signed affine RNG state; Fernz keeps the low 31 bits
that determine the shared output sequence. The inactive counter is normalized
to zero outside counting mode. Counting mode's inactive affine state need not
match for the next draw to agree. Synthetic continuation tests cover counting,
affine, and host-seeded sequences, a switch between modes, and `random 0` after
transfer. See [RNG compatibility](RNG.md) for the behavioral contract.

The reference tuple does not capture the external host seed policy. The adapter
therefore requires an explicit positive seed and rejects export when Fernz's
saved host seed differs. The caller must configure the Jericho recipient with
that seed; it cannot be recovered from the tuple.

Only continuation output is compared. Fernz does not retain a prior observation,
and the adapter does not synthesize one. Screen output must remain enabled;
stream selection is not represented by the observed tuple.

## Validation and limits

The required Linux reference CI job runs:

- Synthetic transfers in both directions at three successive input boundaries,
  checking nested calls, locals, argument counts, evaluation stacks, input
  operands, high addresses, RNG continuation, and reseeding.
- Rejection tests for malformed registers, arrays, frame links, RNG state,
  inconsistent input, mismatched host seeds, and excess stack capacity.
- Six Zork I handoffs: after commands **35, 214, and 350**, in each direction.
  Only the donor plays the prefix. The recipient then plays the full remaining
  route without another import, matching transcript, reward, quit status, score,
  and moves against the uninterrupted reference through the **350-point ending**.
  The existing explicitly asserted presentation and final-move differences
  still apply; conversion introduces no additional normalization.

Run them with the documented reference environment:

```sh
uv run --no-sync poe test-reference
```

This adapter supports the measured V3 snapshot layout and pending reads only.
It does not handle other versions, mid-instruction or halted transfers,
additional output streams, changed call-site store bytes, or stacks beyond the
reference's measured capacity. Arrays and registers are checked before creating
a converted snapshot, but this remains a test helper for trusted checkpoints,
not a deserializer for arbitrary input. Any new reference version or platform
needs fresh public-API measurements and passing continuation tests.
