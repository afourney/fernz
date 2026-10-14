# Embedding Fernz: input, lifecycle, and persistent checkpoints

These APIs let applications use Fernz without importing its private input,
frame, output, or RNG classes. They support V3, V4, V5 and V8 execution.

## Input and lifecycle queries

All three properties are cheap, read-only queries. They do not construct a
checkpoint, execute instructions, invoke callbacks, or draw randomness.

| Current state | `initialized` | `awaiting_character` | `done` |
| --- | --- | --- | --- |
| Before reset or restoration | False | False | False |
| Waiting for a line | True | False | False |
| Waiting for a character | True | True | False |
| Normal interpreter quit | True | False | True |
| Execution invalidated by an error | False | False | False |

`initialized` means an execution context exists, including after normal quit.
Successful `reset()` or `set_state()` makes it true. The host knows from its
own operation history whether an absent context is new or failed.

At a character prompt, `step("")` supplies Enter and `step(" ")` supplies Space.
Case is preserved and only the first character is consumed. At a line prompt,
the action is a command line. Remove host line terminators before calling
`step()`; for example, `action.rstrip("\r\n")` preserves meaningful spaces.
Do not discard a space-only action when `awaiting_character` is true.

Errors have the following lifecycle effects:

| Operation or error | Effect |
| --- | --- |
| `step()` rejects an action type, unsupported input character, or nonpositive/noninteger instruction budget | Preserves the episode; correct the input and retry. |
| `step()` encounters an invalid input buffer, illegal execution, an unsupported opcode, or exhausted instruction budget | Invalidates execution; reset or restore a checkpoint. Memory may contain partial changes. |
| A save/restore callback raises a programming exception or returns the wrong type during execution | Invalidates execution; the exception propagates. |
| A storage callback raises `OSError`, or storage is unavailable/cancelled | Reports ordinary opcode failure to the story, which continues. |
| `reset()` fails, including an invalid budget | Leaves no initialized execution context; the preceding episode has been discarded. |
| `set_state()` rejects a checkpoint | Preserves the receiving environment, including an existing episode. |
| A status/object query rejects a request | Does not invalidate execution. |

Check `initialized` after catching a command error rather than inferring the
effect solely from the exception class. For example, a host callback's
`ValueError` occurs during execution, while an unsupported input character's
`ValueError` occurs before execution. No automatic rollback is performed.

## Reusing a loaded story

```python
from fernz import FernzEnv, Story

story = Story.from_file("games/zork1.z5")
first = FernzEnv(story, seed=12, screen_width=80, screen_height=25)
second = FernzEnv(story, seed=42)
```

The constructor accepts either the existing path forms or a `Story`. A
story-backed environment shares the immutable image and header, creates its own
mutable memory, and has `game_path is None`. The Story does not retain a source
path; moving or deleting the original file has no effect on these environments.
Each environment has its own execution, RNG, and callback bindings. Applications
own any external resources captured by the callbacks they supply.

Seed, save/restore handlers, and screen options work exactly as with a path.
Construction neither runs the opening nor seeds an RNG. Call `reset()` to start
fresh or `set_state()` to resume without executing the opening. `copy()` also
preserves a story-backed environment's absent path.

## Serializing and restoring checkpoints

```python
from fernz import FernzEnv, GameState, Story

story = Story.from_file("games/zork1.z5")
env = FernzEnv(story, seed=12)
env.reset()
payload = env.get_state().to_bytes()

# Store payload in the application's save envelope or as a binary file.
# Validate and prepare a replacement without touching the live environment.
state = GameState.from_bytes(payload, story=story)
candidate = FernzEnv(story)
candidate.set_state(state)
observation, reward, done, info = candidate.step("look")
```

`to_bytes()` serializes the complete `GameState`: story identity, dynamic RAM,
PC, routine frames, pending input, RNG state and active host seed policy,
logical output state, and execution/outcome flags. Supply a checkpoint obtained
through `get_state()`. There is no dependency on pickle, Jericho, NumPy, or an
application-specific codec.

`from_bytes(payload, *, story)` requires the matching immutable `Story` and
accepts bytes, bytearray, or memoryview. It validates the format, field sets,
component types and bounds, input/frame consistency, RNG and output state,
story identity, and protected RAM header fields. It returns an immutable
`GameState`; it does not modify an environment, execute a VM, or consume entropy.
Malformed payloads, unsupported versions, and mismatched stories raise
`ValueError`; wrong argument types raise `TypeError`. `set_state()` validates
again before changing the receiving environment. Structural checks do not
establish that arbitrarily edited RAM represents a meaningful game position.

Host callbacks and external resources are excluded. Supply save/restore handlers
to the candidate constructor if needed; restoring a checkpoint retains those
handlers. The application continues to own the last observation, rendered screen
cells, maps, comments, and save-envelope metadata. A pending seed change made by
`seed()` is also outside the checkpoint: restoration adopts the captured active
RNG's host policy, as it does for in-memory checkpoints.

This format is separate from [Quetzal saves](SAVE_RESTORE.md). It preserves the
RNG exactly. With `seed=None`, later reset/restart/`random 0` operations still
request new entropy; applications that reseed after loading should do so as an
explicit policy.

## Format and portability policy

The payload is UTF-8 JSON with `"format":"fernz-checkpoint"` and
`"format_version":5`. RAM is a standard base64 string; immutable tuples use
JSON arrays. Input records retain the stored-result and character flags when
present. Ordinary-mode RNG records contain Python's version-3 MT state as
integers, including its position. The JSON contains no module or class names to
import and no executable-object deserialization instructions.

Only schema **5** is accepted. Earlier or unknown schema versions are rejected;
there are no compatibility shims or migrations. The schema number is independent
of the Fernz package release number. Changes to this representation require an
explicit schema/version decision. Applications should treat the payload as opaque
and use the public decoder rather than reconstructing private dataclasses.

The current format is tested across CPython **3.11–3.14**, with macOS, Windows
x64, and Windows ARM also checked on Python 3.12. Fixed synthetic checkpoints
pin both predictable and ordinary-mode RNG continuation in those CI jobs.
Future Python RNG implementation/state changes need explicit validation; this
policy does not promise reproducible draws on untested future runtimes.
Character encoding and integer representation are independent of host byte order.
