# Fernz overview

Fernz is intended to become a Z-machine interpreter for common Z-machine story
formats. The project is in its initial setup and documentation stage.

## Mandatory clean-room requirement

**Fernz must be a clean-room reimplementation. Do NOT read or inspect Frotz or
Jericho source code.** This requirement applies to all implementation, debugging,
and testing work on Fernz.

- **Implement independently from the specifications.** Use the Z-machine
  standard and its annotated companion for interpreter behavior, and Jericho's
  public API documentation for API compatibility.
- **Do not copy, port, translate, or derive Fernz code or design from Frotz or
  Jericho source code.** This includes source found in their repositories,
  installed packages, or vendored copies.
- **Black-box functional comparison is allowed.** Frotz or Jericho may be run
  through their public interfaces to compare inputs, outputs, and observable
  behavior, and to support functional tests. Permission to run them does not
  permit inspecting their implementation.

The Jericho repository link below identifies the upstream project only. It is
**not permission to browse its source or use it as an implementation reference**.
This requirement supersedes the earlier proposal to use Jericho's source as a
reference.

## Project goals

- Provide an installable Python package that can be used as a library.
- Mirror Jericho's Python API, or get as close as practical. The exact compatibility
  scope has not yet been decided.
- Implement the interpreter in pure Python as much as possible.
- Potentially provide a minimal interactive CLI for manual testing and playing
  through test games.

The Z-machine specifications will guide interpreter behavior. Jericho's public
API documentation will guide API compatibility, subject to the clean-room
requirement above.

## References

- [Z-machine Standard 1.1](https://inform-fiction.org/zmachine/standards/z1point1/index.html)
  — the primary specification reference.
- [Annotated Z-machine specification](https://zspec.jaredreisinger.com/)
  — a companion reference for explanations and implementation notes.
- [Jericho quickstart documentation](https://jericho-py.readthedocs.io/en/latest/tutorial_quick.html)
  — examples of the library API and its use.
- [Jericho upstream project](https://github.com/microsoft/jericho)
  — project identification only; **do not inspect its source code**. Running
  Jericho for black-box functional testing and comparison is allowed.
- [BYU-PCCL Z-machine game collections](https://github.com/BYU-PCCL/z-machine-games)
  — the source of the test games.
- [Game collection ZIP download](https://github.com/BYU-PCCL/z-machine-games/archive/master.zip)
  — the archive used during setup.

## Environment setup so far

1. Started with the existing `fernz` repository and Python package scaffold.
   `pyproject.toml` declares Python 3.11 or later, uses the `uv_build` build backend,
   and currently declares no runtime dependencies. Package source is under
   `src/fernz/`.
2. Confirmed that a local `.venv/` already exists and uses CPython 3.12.14. This
   environment was present before the game collection setup; it was not created
   as part of these steps.
3. Downloaded the BYU-PCCL archive linked above, verified its ZIP integrity, and
   extracted its contents into `games/`. The nested large game collection was
   also unpacked initially.
4. Kept only `games/jericho-game-suite/`. Removed the Autoplay suite, the large
   game collection, the downloaded archives, and the collection-level README.
5. Removed **Leather Goddesses of Phobos** (`lgop.z3`) from the Jericho suite.
   The retained suite now contains **56 game files**. Verified that those files
   were unchanged during cleanup.
6. Created `docs/OVERVIEW.md` to record the project direction, references, and
   setup history.

The games are available as inputs for future testing. They have not yet been run
with Fernz. Some story filename extensions differ from the version recorded in
their headers, so future version detection should use the story header.

## Test fixture setup

Install the development dependencies with `uv sync --dev`, then run tests with
`uv run pytest`. Tests that need ROMs can request the session-scoped
`jericho_games` pytest fixture, which returns the path to
`games/jericho-game-suite/`.

When the repository's `games/` directory is absent, the fixture downloads the
BYU-PCCL ZIP linked above and extracts only the Jericho suite, excluding
`lgop.z3`. Extraction is staged before creating `games/`, so a failed download
or extraction can be retried. The ZIP and other collections are not retained.

An existing `games/` directory is left untouched and does not trigger a download.
If it lacks `jericho-game-suite/`, the fixture reports an error. Tests that do not
request the fixture do not download games. Downloaded ROMs are ignored by Git.
The download currently follows upstream `master`; it is not yet pinned to an
immutable revision. This download mechanism does not establish redistribution
rights for the games.

## Development tasks and continuous integration

The development workflow adapts the Poe tasks and CI structure from
[cabin-fever-x86](https://github.com/afourney/cabin-fever-x86/blob/main/pyproject.toml)
and the package validation from
[jlv](https://github.com/afourney/jlv/blob/main/.github/workflows/release.yml).
Run `uv sync --dev` to install the locked development tools, then use:

| Command | Purpose |
| --- | --- |
| `uv run poe check` | Check formatting, lint, and spelling. |
| `uv run poe fix-all` | Apply formatting and automatic lint fixes. |
| `uv run poe test` | Run pytest. |
| `uv run poe build-check` | Build the wheel and source distribution, validate their contents, and smoke-test an isolated wheel installation. |
| `uv run poe check-all` | Run all of the above checks, tests, and build validation. |

Individual tasks include `format`, `format-fix`, `lint`, `lint-fix`, `spell`,
`build`, and `check-dist`. Build validation expects one wheel and one source
distribution in `dist/`; remove stale distributions after changing versions.
Formatting and lint cover `src/`, `tests/`, and `scripts/`. Spelling checks also
cover documentation and CI configuration, but exclude test inputs and ROMs.

`.github/workflows/ci.yml` runs on pull requests, pushes to `main`, and manual
dispatch. Separate jobs check code quality and lockfile consistency, run pytest
on Python 3.11 through 3.14, and validate the built package. CI uses the same Poe
tasks as local development, with frozen dependency installation. Superseded runs
are cancelled and workflow permissions are limited to reading repository contents.

The package check verifies metadata, package files, the `py.typed` marker, and
that neither distribution contains game ROMs. It then installs the wheel into a
temporary virtual environment and imports Fernz independently of the checkout.
There is no publishing workflow.

Tests may download the Jericho corpus through `jericho_games` when needed. CI
does not cache or upload ROMs. The current tests exercise fixture management;
interpreter conformance and gameplay tests will be added with the interpreter.

## Current scope

Work includes test-data fixtures, CI checks, and a minimal packaged CLI and
library contract. No interpreter execution is implemented. The precise supported
story versions and broader API coverage remain to be decided.

## CLI and library scaffold

After `uv sync --dev`, run `uv run fernz --help` or
`uv run python -m fernz --help`. The installed `fernz` command targets
`fernz._cli:main` inside `src/fernz/`. The implementation modules `_cli.py` and
`_env.py` are private; use `from fernz import FernzEnv` for the public library
interface and `fernz` or `python -m fernz` for the public CLI.
`fernz GAME` accepts a path to an existing regular file. Help exits with 0,
missing/invalid arguments or paths exit with 2, and an existing file produces a
clear not-implemented message on stderr and exits with 1. There is no interactive
prompt or VM execution yet. The CLI delegates to the public library.

The deliberately small public contract is:

| Interface | Contract |
| --- | --- |
| `from fernz import FernzEnv` | Public environment class; no Jericho runtime dependency. |
| `FernzEnv(game_path)` | Accepts a string or text path-like object. Validates a regular file and stores a `Path` in `game_path`. Missing/inaccessible paths raise `OSError` subclasses; non-regular paths raise `ValueError`. Does not read or validate story bytes. |
| `env.reset()` | Planned result: `(observation: str, info: dict[str, object])`. Currently raises `NotImplementedError`. |
| `env.step(action: str)` | Planned result: `(observation: str, reward: int, done: bool, info: dict[str, object])`. Currently raises `NotImplementedError`. |
| `env.close()` | Idempotent resource cleanup; currently a no-op because no resources are held. |

The tuple shapes follow the permitted
[Jericho public quickstart](https://jericho-py.readthedocs.io/en/latest/tutorial_quick.html).
Future metadata may include score and move count; the scaffold returns no
invented observations, rewards, or metadata. This is an interface outline, not a
claim of drop-in Jericho compatibility. The original `hello()` helper remains
available for compatibility with the initial package scaffold.

Caller-side context was limited to the root
[`play_jericho.py` in cabin-fever-x86](https://github.com/afourney/cabin-fever-x86/blob/b4933c8b167635c9ffbd7cd8ffd1307fc0b3d52e/play_jericho.py).
That consumer uses construction, reset, text steps, and cleanup. Its additional
save restoration, location lookup, score/move queries, and game-over/victory
queries are deferred. Its direct `frotz_lib` access is outside this public
contract; binary saves and interpreter internals are not supported. No Frotz or
Jericho implementation source was inspected or copied.

Scaffold tests use temporary synthetic files without requesting the game fixture
or downloading ROMs. Package validation also exercises the installed command and
module entry point from a temporary directory outside the checkout.
