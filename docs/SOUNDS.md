# Sound behavior and proposed stream commands

**Status: design notes only. Sound playback, sound stream commands, and playback
completion callbacks are unimplemented.** This document records the current
behavior and a proposal for future work; the proposed tags and host interfaces
are not part of the implemented API.

## Current behavior

Fernz recognizes `sound_effect` during V3 and V5 execution, but its handler does
nothing. It does not load resources, play sounds (including simple beeps), emit
sound tags or placeholder text, or register or invoke completion routines.
Normal instruction decoding and operand evaluation still occur.

Neither `Observation.stream` nor `Observation.text` receives anything from a
sound instruction. Any accompanying story narration comes from the game's
ordinary printing instructions. There is no audio backend or host API for
reporting that playback has finished.

The game learns about unavailable sound as follows:

| Version | Capability signaling |
| --- | --- |
| V3 | There is no equivalent standard sound-availability flag. Sound instructions are silently ignored. |
| V5 | A game requesting effects beyond a beep sets **Flags 2, bit 7** in its story header. Fernz clears this bit when configuring the execution header, indicating that it cannot provide those effects. |

Flags 2 is the word at header address `0x10`; its sound bit has mask `0x0080`.
Clearing it lets a game choose a sound-disabled path. It does not prevent the
game from executing sound instructions, and it does not automatically skip or
execute any game routine. The flag concerns effects beyond beeps; it does not
advertise beep support. Fernz currently provides neither.

Existing gameplay comparisons exercise this silent behavior. They do not
establish compatibility with sound-enabled play or prove that every game's
completion routines are harmless.

## Specification contract

The opcode is available from V3:

```text
sound_effect number effect volume routine
```

The operands depend on the operation; they are not all required on every call.

| Operand | Meaning |
| --- | --- |
| `number` | `1` requests a high beep and `2` a low beep; the other operands must be omitted for these. Numbers from `3` identify external sound resources. Number `0` with stop or finish means all sounds. |
| `effect` | `1` prepares a resource, `2` starts it, `3` stops it, and `4` finishes with it (stopping it if necessary and allowing its resources to be released). |
| `volume` | The low byte is a level from `1` through `8`, or `255` for the loudest possible level. In V5 and later, the high byte is the **total number of plays**, from `1` through `254`, or `255` for indefinite repetition. |
| `routine` | In V5 and later, an optional packed routine address to call with no arguments after natural completion of all requested plays. |

In V3, the volume's high byte must be zero; opcode-specified repeats and
completion routines are unavailable. A zero play count in V5 is invalid, but
the specification suggests treating it as one play. An instruction with no
operands is also invalid; the specification asks interpreters to treat it as a
high beep if possible and not halt.

V7 and V8 use the V5 sound interface. Their different address-packing rules
still apply when resolving a routine address. The Flags 2 sound request also
applies in V5 and later. V6 additionally has a sound capability flag at
**Flags 1, bit 5**. These are specification notes, not claims of execution
support beyond Fernz's current V3 and V5 support.

Sound resources are external to the raw story image. Resource lookup and
formats, including Blorb, need a separate host design. Under Standard 1.1,
samples and music are separate types: one of each can play concurrently.
Starting a new sound stops the previous sound of the same type; music and
samples do not interrupt each other. Resource data determines the type.

## Proposed stream schema

Sound commands would join the single ordered `Observation.stream` described in
[Observations and display streams](OBSERVATIONS.md). They would use the same
compact syntax: space-separated arguments, no closing tags, and no self-closing
slash. Existing literal-text escaping (`<<` for `<`) would remain applicable.

| Proposed command | Meaning |
| --- | --- |
| `<beep high>` | Request the high beep, sound number 1. |
| `<beep low>` | Request the low beep, sound number 2. |
| `<sound load ID>` | Prepare the resource as a caching hint; do not play it. |
| `<sound play ID VOLUME PLAYS>` | Start the resource with the specified volume and total play count. |
| `<sound stop ID>` | Stop this sound if it is playing, without invoking its completion routine. |
| `<sound unload ID>` | Stop this sound if needed and release its cached resources, without invoking its completion routine. |
| `<sound stop all>` | Stop both samples and music. |
| `<sound unload all>` | Stop both samples and music and release cached sound resources. |

`ID` is the decimal resource number, at least `3`. `VOLUME` is `1` through `8`
or `max`; `PLAYS` is a positive integer through `254` or `loop`. All three play
arguments would be explicit. The interpreter would unpack the opcode's volume
word before emitting the command. V3 requests would use one play; a V5 zero
play count would also normalize to one under the suggested compatibility rule.

Examples of the proposed commands:

```text
<beep high>
<sound load 7><sound play 7 8 3>
<sound play 7 max loop>
<sound stop 7><sound unload 7>
<sound stop all><sound unload all>
```

The second example requests three total plays, not an initial play followed by
three repeats. Loading is optional, and unloading is a resource-management hint;
a frontend need not maintain a cache.

Audio would be global: selecting `<top>` or `<bottom>` would not affect it, and
sound commands would not move either cursor or change the split. They would
contribute nothing to `Observation.text`, including no automatic `[sound]`
placeholder. Their position in the unified stream would preserve the order of
sound requests relative to text and display operations, not elapsed playback
time or a guarantee that playback has completed.

## Completion callbacks

A completion callback is game code running inside the Z-machine, not a Python
callback embedded in the stream. Standard §9.4.4 says:

> A game should not place any important code in such a routine.

The intended uses include fading or chaining sounds. This is a recommendation,
not a restriction on what the routine can do: it can change variables, objects,
or RNG state. Advertising sound support therefore requires correct callback
handling, even when a routine appears to do only audio bookkeeping.

The routine runs only after the sound naturally finishes all requested plays.
Explicit stopping, unloading, or replacement by another sound must not trigger
it. An indefinitely looping sound has no natural completion. Failed playback
must not be mistaken for successful completion.

One proposed extension is a token identifying an individual playback:

```text
<sound play 7 8 3 @42>
```

The host would report that playback `42` finished. Fernz would retain the
association between the token and the packed game routine internally; routine
addresses would not appear in the stream. The token distinguishes successive
plays of the same resource so that a late completion notification cannot invoke
the wrong routine. Stopped, replaced, or already completed playbacks would no
longer accept completion notifications.

The token syntax and completion-reporting API are proposals, not finalized
interfaces. No such notifications are currently accepted, and Fernz does not
simulate completion merely because a sound instruction was executed.

## Questions to resolve before implementation

- How the host supplies resources, identifies sample versus music, and reports
  availability so the header agrees with actual support. Emitting a tag alone
  is not sufficient to advertise playback support.
- How requests reach the host while the VM is still executing or waiting for
  input. Observations currently return at execution boundaries, which does not
  itself provide an asynchronous playback or interrupt mechanism.
- When completion notifications enter the VM, how their routines resume the
  interrupted execution, and how resulting output is returned to the caller.
  Callback delivery must avoid re-entering the interpreter unsafely.
- How playback tokens and pending callbacks interact with reset, restart,
  `copy()`, checkpoints, and save-file restoration. Notifications from an older
  episode or abandoned state must not affect the current game. Whether the
  existing `<reset>` command also cancels audio remains to be defined.
- How headless tests control completion events deterministically, and how
  muted playback differs from unavailable resources or failed playback.
- How to handle the historical timing behavior described in §9's remarks for
  The Lurking Horror: a new sample may need to wait for the current sample's
  first cycle if both were started since the last keyboard input. Music still
  interrupts music immediately. Stream order alone cannot model this timing.

Future validation should use specification-built stories to check capability
flags, tag ordering, repeat counts, both sound types, cancellation, stale
notifications, and completion routines that visibly change game state. Any
reference comparisons must remain black-box tests through public interfaces,
under the [mandatory clean-room requirement](OVERVIEW.md#mandatory-clean-room-requirement).

## References

- [Z-machine Standard 1.1, §9: Sound effects](https://inform-fiction.org/zmachine/standards/z1point1/sect09.html)
- [Standard §15: `sound_effect`](https://inform-fiction.org/zmachine/standards/z1point1/sect15.html#sound_effect)
- [Standard §11: The header](https://inform-fiction.org/zmachine/standards/z1point1/sect11.html)
- [Annotated Z-machine specification](https://zspec.jaredreisinger.com/)
