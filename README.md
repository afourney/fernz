# Fernz

Fernz is a clean-room, pure Python reimplementation of
[Jericho](https://github.com/microsoft/jericho) and its underlying
[Frotz](https://github.com/DavidGriffith/frotz) Z-machine engine, with a familiar
Python API for playing and exploring interactive fiction.

It is also an experiment in agentic coding: to see how far Astra could get with
a public specification and a black-box reference implementation.

It was built to enable cross-platform play and redistribution in
[Cabin Fever x86](https://github.com/afourney/cabin-fever-x86), and to make
Z-machine games easy to embed, test, and experiment with from Python.
Fernz is [MIT licensed](LICENSE) and runs on Linux, macOS, and Windows.
Here, clean-room means implementing independently from open specifications and
documented public APIs, using the original interpreters only for black-box
behavioral comparisons.

It currently plays **V3, V4, V5, and V8** stories and inspects V1–V8 files.
The API covers gameplay, checkpoints, score/move queries, and object inspection;
some Jericho methods and Z-machine features remain unimplemented.

## Install

Requires **Python 3.11+**. Include the optional
[Textual](https://textual.textualize.io/) terminal interface:

```sh
python -m pip install "fernz[textual]"
```

Use `pip install fernz` for the dependency-free library and simple terminal player.

## Get a game and play

Bring a raw Z-machine story file, or download Zork I from the
[BYU-PCCL game collection](https://github.com/BYU-PCCL/z-machine-games) with Python:

```python
from urllib.request import urlretrieve

url = "https://raw.githubusercontent.com/BYU-PCCL/z-machine-games/master/jericho-game-suite/zork1.z5"
urlretrieve(url, "zork1.z5")
```

Games are distributed separately and retain their own copyrights and licenses.
This Zork I file contains a V3 story despite its `.z5` extension.

```sh
fernz --rich zork1.z5
```

Try `look`, `open mailbox`, and `read leaflet`. Press **Ctrl+Q** to exit.
Textual is selected automatically when installed; `--simple` selects plain text.
The game's `save` and `restore` commands open file dialogs.

## Use the API

```python
from fernz import FernzEnv

env = FernzEnv("zork1.z5", seed=42)
try:
    observation, info = env.reset()
    print(observation.text, end="")
    for command in ("open mailbox", "take leaflet", "read leaflet"):
        observation, reward, done, info = env.step(command)
        print(observation.text, end="")
        if done:
            break
    checkpoint = env.get_state()
    env.step("look")
    env.set_state(checkpoint)
finally:
    env.close()
```

Observations provide plain `.text` and an ordered `.stream` with display tags.
`reward` is the score change, `info` includes score and moves for supported games,
and `done` means the interpreter has quit. Checkpoints include RNG state for
reproducible replay; `env.copy()` forks an environment for independent exploration.

## Further reading

[Detailed guide](docs/GUIDE.md) · [Terminal controls](docs/CLI.md) ·
[API and project overview](docs/OVERVIEW.md) · [Testing](docs/TESTING_PHILOSOPHY.md)

Specifications: [Z-machine Standard 1.1](https://inform-fiction.org/zmachine/standards/z1point1/index.html),
[annotated edition](https://zspec.jaredreisinger.com/),
[Quetzal save format](https://inform-fiction.org/zmachine/standards/quetzal/index.html),
and [Jericho's public API](https://jericho-py.readthedocs.io/en/latest/tutorial_quick.html).
