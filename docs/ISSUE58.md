# Lost Pig instruction-budget investigation (issue 58)

The failure is a host execution-policy limit interrupting finite story work.
No interpreter opcode correction was needed to finish the measured turns.
The fix raised the shared default from 250,000 to 1,000,000 instructions
(`DEFAULT_MAX_STEPS` in `src/fernz/_machine.py`), retaining explicit limits and
the existing failure contract. The rest of this page records the investigation.

## Provenance

- Freshly fetched main: `26960050b9538f0f5137415af01d9e3ceb25388f`.
- Reproduced first on exact failing commit:
  `d579abb5ec2d722c3723c260d4af36ddc2b09ebd`.
- Main differs only in Textual test synchronization; its unpatched minimal
  reproduction also fails. Patch and regression tests are based on fresh main.
- Fernz source version: `0.0.2` in pyproject.toml. Executed with `PYTHONPATH=src`,
  CPython 3.12.14, Linux x86_64, Textual 8.2.8. The pre-existing environment's
  distribution metadata initially said 0.0.0a1; it does not identify the executed source.
- Lost Pig: V8, release 2, serial 080406, Inform 6.30; 285184 bytes;
  header and calculated checksum both `0xa377`.
- ROM SHA-256:
  `7bffe25e933aa22a2b1e9bfc8073bee5687d79a70394da19e50bfed5755368c4`.
- ROM obtained from the repository's documented BYU-PCCL game collection.
- Reference: Debian binary package `frotz_2.54+dfsg-3_amd64.deb`, dfrotz 2.54.
  Only its executable interface was used. No reference interpreter source,
  walkthrough, winning route, or game source was consulted.

## Minimal deterministic reproduction

On the failing build or unpatched main:

```python
from fernz import FernzEnv

env = FernzEnv("lostpig.z8", seed=1, screen_width=100, screen_height=30)
env.reset()
checkpoint = env.get_state()
env.step("light torch")  # budget exhausted at 0x296b5
```

One command is sufficient. No exploration, statue interaction, green pole,
parser rejection, or cave state is required. For comparison on the patched
build, explicitly pass `max_steps=250_000` to reproduce the old failure.
After failure, restore `checkpoint` before retrying; the public environment
intentionally invalidates its active machine on execution failure.

```python
env.set_state(checkpoint)
observation, reward, done, info = env.step("light torch", max_steps=1_000_000)
assert info == {"score": 0, "moves": 1}
assert not done
# A subsequent env.step("look") works.
```

The complete original sequence is preserved without edits in
[tests/routes/lostpig_issue58.txt](../tests/routes/lostpig_issue58.txt).
Replay its lines after reset with seed 1 and 100x30 geometry. The first 37
complete at score 1 / move 36; input 38 fails at exactly `0x140db` under the
old limit. This reproduces the issue's command, score, move, and program counter.

## Measurements and seed dependence

Counts are calls to Machine._execute, including the instruction that requests
input. Instrumentation observes execution without changing opcode behavior.
All diagnostic executions were bounded at 1,000,000 instructions.

| Scenario | Host seed | Instructions for light torch | Result |
| --- | --- | ---: | --- |
| Fresh start | 0, 1, 2, 42, 12345 | 263,251 each | Next input, score 0 / move 1 |
| Fresh start | None, three independent runs | 263,251 each | Same response |
| Original 38 inputs | 1 | 345,476 | Next input, score 1 / move 37 |
| Original 38 inputs | 42 | 329,291 | Same final response and status |
| Original 38 inputs | None, one independent run | 343,945 | Same final response and status |

The original route's cost depends on RNG/state. Seed 1 reliably reproduces
its exact reported stop address. The fresh-start reproducer did not depend
on seed in the tested sample. The original GUI run's unknown RNG state cannot
be reconstructed; it is not needed for this reproduction.

## Control flow and semantics

`Machine.run` counts instructions from zero on every call, stopping at the next
input request or quit. `FernzEnv.step` clears its machine reference while running,
so the thrown ExecutionError leaves it unusable until reset/set_state.
RichCLI then disables the command input. This is not a cumulative move budget
or a Textual/truecolor rendering error.

At the reported stop address, the *next* instruction is `get_child local1 -> sp`
with a branch-on-false offset of 2. In the seed-1 trace, local1 is object 171.
It is part of repeated object/scope traversal:

- `0x14057`: get the parent's first child into local4.
- `0x1405b`: test local4 for zero to terminate this sibling walk.
- `0x1405e`: save its sibling into local5.
- `0x14062`: call packed routine 0x280e (byte 0x14070), with the current object.
- `0x14069`: advance local4 to local5; `0x1406c` jumps back to the zero test.
- `0x140db`: inspect the current object's children, then its property 37
  (`get_prop_addr` at `0x140f7`), returning at `0x1415f` when appropriate.

Near the cutoff, the walk advances from object 171 to 172. Across the completed
turn, `0x140db` executes 8,764 times over 28 object IDs; most of its frequently
visited objects are examined 547 times. The sibling-loop zero test executes
9,312 times. Repetition alone is not a nonterminating VM state: caller state
and traversal objects advance. At instruction 345,476 the story executes
`aread` at `0x12099` and yields. This is consistent with repeated scope tests
while resolving an omitted ignition source; that high-level purpose is inferred
from bytecode flow and the independently observed response, not game source.

A follow-up profile assigns instructions to their executing routine (exclusive
counts, so these rows do not double-count nested calls):

| Routine byte address | Calls | Instructions | Share | Observed operations |
| --- | ---: | ---: | ---: | --- |
| 0x14070 | 8,764 | 98,190 | 28.4% | Visit an object, check child and property 37 |
| 0x13fb8 | 8,737 | 96,125 | 27.8% | Dispatch by traversal mode; in mode 6 compare object with a target |
| 0x14040 | 1,642 | 48,751 | 14.1% | Walk child/sibling lists and invoke the visitor |
| 0x29658 | 1,686 | 41,321 | 12.0% | Type/property tests, including searching words of property 2 |
| All remaining routines | — | 61,089 | 17.7% | Other parsing, dispatch, action handling, output and next input |

The top four opcode counts are `je` 68,787, `store` 64,130, `jz` 43,993,
and `jump` 33,420: together 60.9% of the turn. These are tiny VM operations,
not source-level statements. For example, each sibling iteration needs several
instructions plus the recursive visitor. Routine 0x14db8 sets traversal mode 6,
sets a target object, runs a traversal, and restores the prior state: it is
consistent with a scope-membership predicate, called 544 times in this turn.
The outer routine at 0x27fb8 initializes its candidate to 1, calls 0x14db8
for that candidate and object 87, increments it, and loops through object 535
(the bound 0x217 is explicit in the bytecode). It executes once, accounting
for 270,212 instructions including its descendants, or 78.2% of the turn.
This is why the same nearby objects are traversed so often: the story performs
a scope-like test separately for each candidate in the entire object table.

The profile does not assign authoritative game-source names to these routines
or claim a separately measured "lighting" phase. The observed response does
not actually ignite anything.

Uninstrumented repeated runs from the same checkpoint took 3.30, 3.44, and
3.71 seconds on this execution host; `look` took 0.47 seconds in each of three
runs. These are local timings, not portable performance guarantees. The full
routine/opcode profile with instrumentation took 5.37 seconds.

The [Z-machine Standard §12](https://inform-fiction.org/zmachine/standards/z1point1/sect12.html)
defines child/sibling links and zero as no object. The
[opcode specification §15](https://inform-fiction.org/zmachine/standards/z1point1/sect15.html)
defines get_child/get_sibling result and branch behavior, and read/aread input
semantics. The inspected implementation follows those operations here; the
250,000 cutoff is Fernz policy, not a specified Z-machine instruction limit.

Black-box comparison:

```sh
dfrotz -m -s 1 -w 100 -h 30 lostpig.z8 < tests/routes/lostpig_issue58.txt
# Also run with a file containing just: light torch
```

Both reference runs complete. Regression expectations are SHA-256 hashes of
whitespace-normalized lower-window responses (without prompt), independently
measured from dfrotz output. The original route's response says an ignition
source is missing; the opening response says the torch is already lit.

The separate online report concerning *examining* a torch and property 90
has not been established as related. The observed loop here uses property 37,
finishes without an opcode change, and matches the black-box response.

## Proposed remedy and validation

Use one `DEFAULT_MAX_STEPS = 1_000_000` constant for Machine.run and both public
execution methods. This is a bounded policy adjustment justified by measured
finite work, not a workaround for a demonstrated opcode defect. It gives roughly
2.9x headroom over the largest observed turn. It does not guarantee every valid
story turn will fit. Truly looping stories may now run four times as many
instructions before failure; explicit caller limits still take precedence.
Existing V8 and readiness documents already record Afflicted exceeding the old
default and use 2,000,000 in its tests. Those paths were not replayed here;
1,000,000 must not be presented as a corpus-wide sufficiency guarantee.
No story-specific exception, save-format change, or GUI change is needed.
Both CLI frontends inherit the new default.

- Default suite: **1110 passed**, 14219 deselected, 21.63 s (pytest 9.1.1).
- `pytest tests/test_lostpig_budget.py -m rom -q`: **2 passed**, 30.81 s.
  Covers old explicit cutoff and invalidation, checkpoint recovery, default
  completion, independent reference hashes/status, full original route, and
  a subsequent usable command.
- Follow-up PR checks: `poe test-fast` **1306 passed**, 14023 deselected;
  both issue regressions **2 passed** again. `poe check` and `poe build-check`
  pass, including formatting, lint, spelling and isolated wheel installation.
  The initial distribution check found two pre-existing 0.0.0a1 build artifacts;
  those were moved outside dist before checking the fresh 0.0.2 artifacts.
- Textual 8.2.8 headless integration at physical 110x34 / logical 100x30 with
  truecolor: `light torch`, then `look`, both leave input enabled (see local log).

The full reference/corpus/winning-route suites were not run: this investigation
intentionally avoided winning trajectories. A release-wide budget assessment
and any configurable CLI budget or recoverable timeout UI are separate work.
The change is intended for a draft PR; merging and release remain separate decisions.

