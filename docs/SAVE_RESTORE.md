# V3 save and restore

Fernz implements the V3 story opcodes `save` and `restore` using Quetzal files.
The implementation follows the [saved-state rules](https://inform-fiction.org/zmachine/standards/z1point1/sect06.html),
[opcode definitions](https://inform-fiction.org/zmachine/standards/z1point1/sect15.html#save),
[header ownership rules](https://inform-fiction.org/zmachine/standards/z1point1/sect11.html),
and the [Quetzal specification](https://inform-fiction.org/zmachine/standards/quetzal/index.html).
Clean-room requirements apply: reference comparisons use public APIs and packaged
executables only.

## Two separate restoration contracts

| State | Host checkpoint: get_state / set_state | Story opcode: save / restore |
| --- | --- | --- |
| Dynamic memory and routine frames | Captured and restored | Captured and restored |
| Continuation | Pending decoded input request, or halted state | Saved save-instruction branch |
| RNG state and host seed | Captured and restored for deterministic replay | Not written; the recipient's current RNG and host seed are retained |
| Output selection | Captured and restored | Current setting retained |
| Flags 2 | Saved value restored | Current value preserved |
| Interpreter-owned header fields | Validated for a Fernz checkpoint | Adapted to the receiving interpreter |
| Representation | Immutable Fernz GameState | Portable Quetzal bytes |
| Host callbacks and external files | Not captured or rolled back | Supplied by the host |

The existing checkpoint schema and behavior are unchanged. Restoring a Quetzal
file in another process recovers the saved game position, but does not promise
the original process's subsequent random outcomes. Opcode restoration itself
neither draws randomness nor obtains entropy.

## Library storage callbacks

Supply optional keyword arguments when constructing an environment:

- `save_handler(data: bytes) -> bool`: store the complete Quetzal data and return
  `True` on success, or `False` for cancellation/failure.
- `restore_handler() -> bytes | None`: return a complete save file, or `None`
  for cancellation/failure.
- `output_handler(text: str) -> None`: optionally receive output fragments as
  execution emits them. This lets a frontend display story output before a
  storage callback prompts for a filename. `reset()` and `step()` still return
  the complete observation, so a streaming frontend should not print it again.

These callbacks are synchronous, must not re-enter the same environment, and
remain attached to the receiving environment across reset and checkpoint
restoration. They run only when needed; construction does not execute a story
or access save storage. No callback is serialized.

`copy()` retains the same callback references. Forked environments have
independent VM state; external storage and output destinations are shared if
the callbacks refer to the same resources.

For example, a test can use an in-memory save slot:

```python
from fernz import FernzEnv

slot = {}

def save_game(data: bytes) -> bool:
    slot["game"] = data
    return True

env = FernzEnv(
    "games/jericho-game-suite/zork1.z5",
    seed=12,
    save_handler=save_game,
    restore_handler=lambda: slot.get("game"),
)
try:
    env.reset()
    env.step("open mailbox")
    env.step("save")
    env.step("take leaflet")
    observation, reward, done, info = env.step("restore")
    # The leaflet is back in the mailbox. slot["game"] contains Quetzal bytes.
finally:
    env.close()
```

Storage may instead be a file, database, or caller-managed service. The VM has
no filename or filesystem policy. `Path.read_bytes` is a suitable restore
callback; a save callback wrapping `Path.write_bytes` must explicitly return a
boolean rather than its byte count.

Absent handlers and `OSError` from storage report ordinary opcode failure.
Malformed, truncated, wrong-story, or invalid-continuation files also report
restore failure, without installing any partial saved state. The game can
handle that result and continue. Invalid callback return types raise
`TypeError`; other callback exceptions propagate as programming errors. A
failed execution still requires reset or a valid host checkpoint before reuse.

## Interactive CLI

Use the game's own SAVE and RESTORE commands:

```sh
uv run fernz games/jericho-game-suite/zork1.z5
```

When the corresponding opcode executes, the CLI asks for a filename. A blank
line or EOF cancels. Saving to an existing file requires an affirmative overwrite
response. Saves are written to a temporary file in the destination directory
and atomically replaced after a complete write; a failed write leaves the
previous file intact. Storage errors are printed to stderr and passed back
to the game as opcode failure.

Prompts read from the same input stream as game commands, so piped sessions
must include the filename and, when applicable, the overwrite response. The
CLI streams story output before prompting and does not duplicate returned
observations. Filename prompts are frontend output, not story observations.

## Saved continuation and validation

A V3 save records its branch-byte address before taking the success branch.
A successful restore applies that saved branch as true, including its polarity,
signed offset, and special return offsets 0/1. A failed save or restore applies
false to the current instruction's branch. A successful restore transfers
control to the saved continuation and never finishes the current restore
instruction's branch.

The codec writes IFhd, CMem, and Stks chunks, including the mandatory initial
dummy frame. It reads CMem and UMem, handles IFF alignment, skips unknown chunks,
and uses the first required component when duplicates occur. Compressed memory
is bounded by the story's dynamic-memory size; frame lengths and addresses are
checked before use. IFhd checks release, serial, and checksum against the loaded
story. This is the format's identity check, not the full image hash used by
Fernz host checkpoints.

Restore stages memory, frames, and the saved branch before changing the live
machine. It preserves the memory object's identity. Current Flags 2 survives,
and interpreter-owned capabilities and Standard version are set for Fernz.
Unsupported V3 frame encodings and invalid continuations fail restoration.

## Validation coverage and scope

Normal tests use independently constructed format vectors and stories. They
exercise compression boundaries, uncompressed memory, chunk ordering and
duplicates, nested calls, branch polarity and returns, malformed data, atomic
rejection, RNG preservation, and unchanged host checkpoints. CLI tests save and
load in separate processes and check cancellation, overwrite confirmation,
output order, and failed-write preservation.

The required Linux reference job exchanges saved files with the standalone
Frotz executable, in both directions. Synthetic stories retain values in every
frame, including return and save addresses above 64 KiB. Zork tests transfer a
position after taking the leaflet and continue into the house; native
continuations compare complete transcripts with identical display settings.
The probes pass with the Frotz 2.54 and 2.55 executables.

The reference job also loads a Fernz save directly into Jericho 3.3.1, using
only its public API. For the Zork fixture, black-box calls establish that
`step("save")` writes `zork1.qzl` in the current working directory without a
filename prompt. Put the Fernz save at that path, load the same ROM, call
`reset()`, then `step("restore")` to resume it. Jericho's documented `load()`
method loads a story ROM, not a save file. The test isolates the working
directory and compares all seven continuation turns, including text, reward,
termination, score, and moves. The file still does not restore RNG state.

A further Zork walkthrough saves and restores after commands 35, 214, and 350,
modifies score memory before each restore, and compares all 396 gameplay
commands with the uninterrupted Jericho reference through the 350-point ending.
It explicitly checks that the inserted save/restore operations do not consume
RNG draws. This does not assume that restoring rewinds randomness.

Execution support remains V3. V4-V8 opcode variants, auxiliary-memory saves,
and undo are deferred. V3 [restart](OVERVIEW.md#host-reset-and-v3-restart) is
supported and retains host storage callbacks and existing save files.
The codec is private; there is no public method to load an arbitrary Quetzal
file before reset. Invoke the story's
restore opcode through the storage callback.
