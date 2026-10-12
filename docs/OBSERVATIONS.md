# Observations and display streams

`FernzEnv.reset()` and `step()` return an immutable `Observation` as their first
tuple element. The other tuple elements retain their existing meanings.

```python
from fernz import FernzEnv

env = FernzEnv("games/zork1.z5", screen_width=80, screen_height=25)
observation, info = env.reset()
print(observation.text, end="")
observation, reward, done, info = env.step("open mailbox")
print(observation.text, end="")
```

This changes the previous string API: consumers should use `observation.text`
where they previously used the observation directly. `observation.stream`
provides the ordered display operations. There are no separate window strings
or split-height field; keeping one stream preserves ordering across windows.

## Two views of the same output

`text` concatenates the plain text emitted to **both** windows, in execution
order. It has no markup, wrapping, or padding added by a renderer. A later
overwrite or clear does not remove earlier text from this transcript. Each call
contains only newly emitted output, including the newline completing line input.
Character input does not add that newline.

For the exact recognized Zork I build, `text` omits the final command prompt
while waiting for lower-window input. It removes a trailing `>` after a newline,
or the trailing ` >` used after some confirmations. Questions, title text,
embedded greater-than signs, and other stories' prompts are preserved. This
narrow rule brings the convenience text closer to Jericho's public observation;
it does not promise byte-for-byte equality for every story or host screen size.

`stream` retains all emitted text, including that prompt, and interleaves display
commands. For example, a story might produce:

```text
<split 2><top><at 1 1><invert>Room name<normal><bottom>You open the door.
>
```

Printing several fragments creates adjacent text, without a tag per fragment.
Tags record actual operations even when no visible text changes. Text sent to
memory output stream 3, or suppressed by disabling screen output, enters neither
observation field. Display operations still apply independently of stream 1.

## Stream grammar

This is a small text protocol, not HTML or XML. Commands have no closing tags or
self-closing slash. Their arguments are separated by single spaces. A literal
`<` in game output becomes `<<`; other characters, including `>`, are unchanged.
A reader must consume `<<` as literal text before recognizing `<...>` commands.
Blindly stripping angle-bracket expressions would corrupt story text. Any UI
that renders HTML must escape decoded story text as usual.

| Command | Meaning |
| --- | --- |
| `<reset>` | Clear the consumer's screen and reset logical state: bottom selected, no split, both cursors at 1,1, normal style, font 1, white on black, lower-window buffering on. |
| `<size WIDTH HEIGHT>` | Set geometry in fixed-width character cells. Emitted immediately after reset. |
| `<top>`, `<bottom>` | Select the destination for subsequent text and window-local commands. Selection alone does not move a cursor. |
| `<split ROWS>` | Set the upper window's height; zero hides it. Total screen height stays fixed. Any resulting clears or cursor moves are explicit subsequent commands. |
| `<at ROW COL>` | Move the selected window's cursor, using one-based screen coordinates. |
| `<at ROW COL top>`, `<at ROW COL bottom>` | Move the named window's cursor without selecting it. Used when an operation moves an inactive window's cursor. |
| `<bold>`, `<italic>`, `<invert>`, `<fixed>` | Enable a style for subsequent text in the selected window. Styles accumulate. `<invert>` exchanges foreground/background appearance; it does not change text order or writing direction. |
| `<normal>` | Clear the selected window's style bits; font and colours remain selected. |
| `<font 1>`, `<font 4>` | Select the normal or fixed-width font for the selected window. A font query emits nothing. |
| `<color FOREGROUND BACKGROUND>` | Set the selected window's colours. Values are palette names, lowercase `#rrggbb`, `default`, or `current`. |
| `<clear top>`, `<clear bottom>`, `<clear all>` | Erase the named area. Erasure itself does not move cursors or change selection, styles, or split; those effects are separate commands. |
| `<clear-line>` | Erase from the selected upper cursor through the right edge without moving it. |
| `<buffer on>`, `<buffer off>` | Set the lower window's buffering policy, regardless of the selected window. The upper window stays unbuffered. |

Palette names are `black`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`,
`white`, `light-grey`, `medium-grey`, and `dark-grey`. `current` retains that
channel; `default` restores the interpreter default for that channel. Consumers may theme defaults independently of explicit palette
colours (including black and white). VM state still resolves defaults to white
on black. True colour expands the Standard's five-bit RGB components to eight bits.

The environment emits effective operations rather than a literal opcode dump.
For example, selecting the upper window emits `<top><at 1 1>`, a V3 split also
emits `<clear top>`, and a supported implicit upper-window expansion emits a
split before its cursor move. Ignored or unavailable operations emit nothing.

Sound instructions currently emit nothing. [Sound design notes](SOUNDS.md)
record the existing sound-disabled behavior and proposed stream commands;
audio playback, sound tags, and completion callbacks remain unimplemented.

## Geometry and lifecycle

`screen_width` defaults to 80 and accepts integers 1–255. `screen_height`
defaults to 25 and accepts integers 1–254. Booleans and non-integers are rejected.
The height sentinel 255 means an infinite screen in the specification and is
not supported by this finite display model. The read-only environment properties
expose the current dimensions. V5 header dimensions and one-cell font units
agree with these settings. V3 has no corresponding header geometry fields.

Every `reset()` starts its stream with `<reset><size WIDTH HEIGHT><bottom>`.
V3 and V4 additionally position the initial cursor at the bottom left. Ordinary
`step()` calls emit deltas and do not reset the display. In-game `restart`
preserves host geometry and emits the operations actually performed by the game.

Host checkpoints use schema **5** and retain geometry, selection,
cursors, fonts, styles, colours, buffering, and memory-output continuations.
`set_state()` restores that state and adopts its dimensions, including for a
fresh receiving environment; subsequent `reset()` uses those dimensions.
`copy()` preserves it too. Restoring emits no output and does not replay the
last observation. Only the current checkpoint schema is accepted. It also
preserves ordinary-mode Python RNG state; see [random modes](RNG.md).

External transcript/command-recording output streams 2 and 4, and file input
stream 1, are unavailable. Selecting or deselecting them is a silent no-op;
execution continues with host input and the existing screen/memory routing.
Flags 2 bit 0 stays clear, including after direct game writes or checkpoint
restoration, because no transcript service is active. Other writable bits retain
their normal behavior. An unconfigured `Memory` used for raw inspection does not
apply this execution-host policy. These requests do not create files or add text
or tags to an observation.

Quetzal files have a different contract. Opcode restore keeps the receiving
environment's geometry, RNG, and host display settings; V3 additionally collapses
the upper window as required by Standard §8.6.1.3. Its stream records that change.

VM checkpoints do not store a screen-cell matrix. A frontend applying these deltas
must checkpoint its own rendered screen alongside the VM checkpoint, or replay
the matching stream history when restoring. A frontend also owns input echo,
wrapping and lower-window scrolling; those are rendering consequences rather
than separate VM scroll commands. The upper window does not scroll. The present
interpreter tracks logical cursors; the optional Textual CLI maintains its own
rendered cells and lower-window scrollback.
V3's separate built-in status line remains unadvertised; explicit upper-window
output is supported. Optional V5 style/colour capabilities remain unadvertised,
although explicit supported style/colour instructions are recorded.

Both CLI frontends accept `--screen-width` and `--screen-height`. The Textual
frontend measures unspecified dimensions from its available game area at startup,
accounting for its controls and scrollbars. Explicit dimensions remain fixed;
resizing changes only the viewport. It renders the ordered stream as a contiguous
logical screen; see [the CLI guide](CLI.md). The `--simple`
frontend uses the existing raw `output_handler(str)` callback so
story prompts and output preceding a save/restore filename request appear
immediately. That callback receives text from both windows, including prompts,
without tags; it does not receive `Observation` objects or renderer events.

## Validation

Specification-built stories test interleaved windows, overwritten/erased text,
escaping, cursor and style commands, colours, buffering, geometry, snapshots,
copy, restart, and file restore. Linux compares synthetic two-window transcripts
and header geometry through **Jericho's public API as a black box**. No Frotz or
Jericho implementation source is consulted.

The existing game comparisons retain their explicit presentation rules. V5
lower-window comparisons and Sherlock's boxed-clue checks now read the public
stream instead of observing private output internals. The old V3 VM fingerprint
projection excludes Fernz-only display state, which the public reference
snapshot cannot supply; full Fernz snapshot replay tests cover that state.
V3 vectors were regenerated for the newly advertised split-window capability.
Archives still contain only commands, metadata, numeric expectations and hashes,
without copyrighted game text, ROM bytes, memory dumps, or save payloads.
