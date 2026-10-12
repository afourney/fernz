# Fast checks and comprehensive validation

Pull requests run [fast.yml](../.github/workflows/fast.yml), named **check** in
GitHub Actions. The complete matrix remains in [ci.yml](../.github/workflows/ci.yml),
named **comprehensive**, and runs only when explicitly dispatched. Pushes to
`main` also run the fast checks. There is no scheduled comprehensive run.

## Fast means bounded work

The PR workflow aims to finish within **three minutes of runner execution**,
including installation and fixture setup. Queue time is outside this budget.
Every job has a five-minute safety limit. Test commands have a two-minute
limit, except portable smoke checks, which allow three minutes for the full
Textual resize matrix and Windows process shutdown. A timeout fails the check;
it does not silently skip remaining tests.
These are guardrails, not a reason to grow the suite to fill the available time.

The automatic checks keep:

- Formatting, lint, spelling, lockfile validation, and package build checks.
- All offline tests on Linux/Python 3.11–3.14 and on macOS, Windows Server 2025
  x64, and Windows 11 ARM with Python 3.12.
- Loading, memory, and CLI inspection checks for all 57 retained stories.
- Headless Textual frontend and rendering checks on Linux and all three portable
  platforms, with the optional `textual` extra installed. The isolated wheel
  check and reference-smoke environment retain dependency-free CLI coverage.
- Each of the 16 V3 games' opening and first five walkthrough commands, with
  full observation, VM-state, and object/query hashes. Short copy, restore,
  and reset checks reuse those same records.
- Integrity checks of every member in all committed vector ZIPs.
- Short live Jericho comparisons on Linux for all 17 V3 games, plus focused
  seed, copy, save/restore, and restart comparisons.

The initial V5 milestone adds the same bounded first-prompt checks for 9:05,
using `905_vectors.zip` portably and live public Jericho calls on Linux.

The short gameplay tests have their own fixtures. They never request full-route
checkpoint fixtures: those execute an entire walkthrough before a test begins.
The five-command limit is fixed, and the selection does not rotate or sample
randomly. Existing assertions and expectations are shared with the full suite.

Poe commands print the slowest tests, including fixture setup. Measure changes
on the hosted runners too, especially Windows x64, before enlarging the fast
selection. Dependency downloads may be cached; game ROMs are never cached or
uploaded. A fresh fixture download is included in the test-step time limit.

## Comprehensive runs are explicit

The manual workflow retains the full Python/platform matrix, all winning
walkthroughs, detours, deaths, alternate seeds, game-specific mechanics,
checkpoint replays, snapshot transfers, and Quetzal file interchange. Linux
compares directly with Jericho through its documented public API and with the
standalone Frotz executable. It also checks every vector archive against fresh
independent measurements. No interpreter implementation source is inspected.

To validate a PR, open **Actions → comprehensive → Run workflow**, select the
PR branch, and run it. The CLI equivalent is:

```sh
gh workflow run ci.yml --ref YOUR_PR_BRANCH
```

Check that the run's commit SHA matches the PR head. Later pushes run the fast
suite automatically but need a new explicit comprehensive run. Run the full
suite before merging interpreter, reference-adapter, scenario, or vector changes,
and before releases. Documentation-only changes normally need only fast checks.
The manual workflow is not an automatic PR merge gate.

Both suites fail when a requested reference or fixture is unavailable. Neither
falls back to a different oracle or rewrites vectors to make a comparison pass.

## Local commands

```sh
uv run poe test          # Offline unit/API tests only; no downloads
uv run poe test-fast     # Offline tests, all story files, short portable gameplay
```

On Linux, after installing the reference dependencies:

```sh
sudo apt-get install --no-install-recommends frotz
uv sync --frozen --python 3.11 --group reference
uv run --no-sync poe test-fast-reference # Short live Jericho checks; no Frotz needed
uv run --no-sync poe test-full           # All tests and vector freshness checks
```

`test-full` runs the existing offline, ROM, live-reference, portable-vector, and
archive-verification tasks. It is intentionally exhaustive. `poe check` and
`poe build-check` remain separate local quality and packaging commands; both
workflows include them.

The V5 corpus expansion uses three `reference V5` jobs and three V5 portable
groups on each hosted OS, selected by `--v5-shard 1/3`, `2/3` or `3/3`.
Groups are balanced by approximate route/object-inspection work. Run them locally with `poe test-v5-reference` and
`poe test-v5-vectors`. The reference job also runs `poe check-vectors --only v5`.
They belong only to the manual comprehensive workflow; the fast workload is
unchanged. See [V5 validation](V5.md) for its exact comparison boundaries.

V8 has dedicated comprehensive Linux reference and portable jobs. The six
gameplay archives are regenerated through public Jericho calls on Linux; portable
jobs replay the same records without Jericho. Quick checks include synthetic
V8 execution, archive integrity and a short Lost Pig opening; see [V8 compatibility](V8.md).

The V8 comprehensive group includes all six winning routes (966 inputs), their
query/counter checks and checkpoint replay. The fast suite also audits all 57
profiles and recorded winning-route metadata without executing full routes.
These full routes are excluded from automatic PR smoke checks.

V4 has a dedicated comprehensive reference/freshness job and portable group for
Trinity. These run its full 610-command winning route, parser detours, loss and
lifecycle scenarios, plus synthetic Quetzal file interchange on Linux. Fast CI
adds only archive integrity and the opening plus five commands, including a
short live reference comparison. See [V4 coverage](V4.md).

## Release packaging

[release.yml](../.github/workflows/release.yml) runs only on `v*` tag pushes and
publishes after version and artifact validation. It does not run on pull requests
or branch pushes. Ordinary CI retains `poe build-check` in its build job.
See [Publishing Fernz](PUBLISHING.md) for the required GitHub/PyPI setup, local
packaging checks and release checklist.
