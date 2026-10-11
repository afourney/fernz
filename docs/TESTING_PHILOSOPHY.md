# Test vectors and cross-platform validation

Fernz is a pure Python, MIT-licensed, clean-room Z-machine implementation.
Its tests should help us improve compatibility while keeping the library
portable and independent of any other interpreter's implementation.

## The specification is authoritative

We implement from the Z-machine specification and documented public APIs.
We do not inspect Jericho or Frotz implementation source. We may run their
public APIs or executables as black-box references to measure behavior.

A reference interpreter is useful evidence, not the definition of correctness.
When behavior differs, investigate the specification and record the reason.
Intentional differences belong in narrow, explicit assertions and documentation;
they must not become broad filters that hide unrelated failures.

## Live comparisons on Linux, recorded expectations everywhere

Linux CI executes Jericho through its public Python API as a black-box test
oracle. It supplies the same inputs to Jericho and Fernz, then compares their
observed outputs and publicly exposed state. We do not read, inspect, or use
Jericho or Frotz implementation source to develop Fernz or its tests. These
live comparisons remain required. Linux also checks committed gameplay vectors
against fresh results from those public API calls, so recorded expectations
cannot silently drift away from the reference.

The macOS and Windows jobs use committed test vectors containing hashes of
expected results. They run Fernz on the actual story files and compare its
outputs and state with those expectations, without installing Jericho. Linux
also runs the vector tests. This gives every platform the same reproducible
behavioral checks while preserving the stronger live comparisons where the
reference is supported.

The two forms of testing are selected explicitly. A missing or broken Linux
reference is a test failure, not a reason to fall back to recorded vectors.
The ordinary synthetic tests also run on every platform and cover small,
independently constructed examples and error conditions.

## Record independent expectations

Gameplay expectations come from public Jericho calls with a pinned reference
version, exact story identity, fixed seeds, and explicit command sequences.
The test-only state adapter translates public snapshots into a portable form
at supported input boundaries. We record canonical fields and hashes rather
than making another interpreter's native memory layout a portable contract.

The additional V3 suites also decode full object records independently from
public snapshot RAM and unchanged story bytes, using Standard §§3 and 12.
This supplies expectations for unnamed nodes, full names, and property lists
that native convenience queries omit or truncate. Only fingerprints enter the
archives; the decoder does not call Fernz's object or text implementation.

Story-file metadata has a different independent source: original file bytes
decoded according to the specification. These vectors check Fernz's loader
without using that same loader to generate its expected answers. They cover
all retained stories' metadata and memory, even where execution support is
still incomplete.

Do not generate expected results by running the Fernz behavior being tested.
That would preserve current bugs instead of providing an independent check.
Likewise, loading a story successfully does not establish that the interpreter
can execute or finish it.

## No copyrighted game content in vectors

**The vector archives contain no copyrighted content from the Z-machine games.**
They contain test commands, factual metadata, and hashes of expected data.
They do not contain game ROMs or bytecode, narrative transcripts, object-table
text, raw memory or stack dumps, or saved-game payloads. When an
expected result includes game content, record its hash rather than its content.

SHA-256 hashes let tests compare complete observations and memory regions
without storing those regions in the repository. They are equality checks,
not playable story images or restorable checkpoints. Fernz's MIT license does
not change the distribution terms of the separately obtained games.

The existing fixture obtains the ROM corpus separately when needed. Tests pin
the expected files by hash; CI does not cache or upload the games directory.
The committed ZIPs are read directly with Python's `zipfile` library and are
never extracted to disk during replay.

## Regeneration is deliberate

Vector generation must be reproducible. Record format versions, reference
provenance, story identities, and scenario definitions. Use deterministic JSON
and ZIP metadata, and include member checksums so missing or damaged data fails
clearly. Keep generation and read-only verification as separate operations.

Regenerate only after understanding the intended change. A failed comparison
is a reason to investigate, not to replace the expected answer automatically.
Review generator or scenario changes together with their updated archives.
CI verifies committed expectations without rewriting them.

Hashes keep the fixtures compact, but cannot show the original expected text
or byte difference. Failures should identify the story, scenario, command, and
field. Use the live Linux comparison to inspect a gameplay mismatch, and the
specification and original bytes to investigate metadata mismatches.

See [the vector guide](VECTORS.md) for archive contents, current comparison
boundaries, platform jobs, and generation and verification commands.
