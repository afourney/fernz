# Playing in the terminal

Install Fernz's optional Textual frontend with:

```sh
pip install 'fernz[textual]'
fernz path/to/story.z5
```

From a development checkout, use `uv sync --extra textual` and
`uv run --extra textual fernz path/to/story.z5`. Textual and its dependencies
are optional; the interpreter library and simple player need none of them.

The CLI chooses Textual when it is installed, otherwise the simple terminal
loop. `--rich` and `--simple` explicitly select a frontend and are mutually
exclusive. Requesting `--rich` without Textual reports an installation hint.
`--inspect` prints metadata as JSON without loading either player UI.

## Download games

Run `fernz --download-games` to extract the test fixture's game files directly
into `./games/`, then play with `fernz zork1.z5`.
Use `fernz --download-games DESTINATION` for another destination and pass the
resulting story path explicitly. Download mode needs no story argument and
cannot be combined with a story or `--inspect`, `--simple`, or `--rich`.
Existing destinations containing `zork1.z5` are reused without modification;
other existing destinations report an error. Failed downloads/extractions
leave no partially installed suite and can be retried.

Playing and inspection first use the exact supplied path. Only a missing
relative path is retried under `./games`, with the same filename and extension.
There is no recursive search or extension discovery; existing-path errors
are preserved. Both missing paths and download failures report an error and
exit with status 2.

## Textual player

The default theme is **Fern & Loam** (`fern-loam`): deep forest green, earthy
brown panels, warm cream text and muted old-gold accents. Use Textual's command
palette (Ctrl+P) to change themes during play. UI surfaces and interpreter-default
story colours follow the selected theme, including existing scrollback. Explicit
story colours and bold, italic or inverted styles remain story-controlled.

When the terminal reports 256-colour support, Fern & Loam automatically uses
charcoal surfaces, muted green, warm brown and old-gold accents chosen from
that palette. The original dark forest palette remains unchanged in true colour.
Only Fern & Loam's theme colours change; explicit story colours still use the
terminal's normal colour conversion. To request true colour in a capable
terminal whose detection falls back, set `TEXTUAL_COLOR_SYSTEM=truecolor` before
launching Fernz. The fallback can be tested with `TEXTUAL_COLOR_SYSTEM=256`.

The upper and lower windows occupy one contiguous logical screen. The lower
window has scrollback; when following live output, older history cannot appear
between the two windows. Surplus terminal rows remain blank below the screen.
The player
applies the ordered [display stream](OBSERVATIONS.md): cursor positioning,
overwriting, clearing, window splits, colours, bold, italic and inverted text.
Both supported fonts use the terminal's fixed-width font. Story text is literal,
so brackets and angle brackets cannot become Textual/Rich markup.

- Type a command and press Enter. Up/Down recall previous commands and preserve
  an unfinished draft. Submitted lines appear once in the lower output.
- When a game requests a single character, press that character directly;
  Enter supplies the return character. The command field is disabled meanwhile.
- Scroll the output with the mouse or trackpad. Scrollback retains up to 2,000
  rows in addition to the current logical screen.
- If the terminal is smaller than the logical screen, scroll the shared game
  viewport to see its other rows or columns. Its horizontal scrollbar sits
  below both windows. Tab to the viewport and use Ctrl+PageUp/Ctrl+PageDown
  to scroll horizontally; Home/End scroll vertically. The live grid keeps its
  coordinates when the viewport changes size.
- Ctrl+Q or Ctrl+D exits. Ctrl+C exits with the usual interrupt status, 130.
  When the story quits, its last output stays visible until you exit.
- Game-issued save/restore requests open a filename dialog. Escape or a blank
  path cancels. Replacing an existing save requires a separate confirmation.
  Saves are written atomically; storage errors return control to the story.

VM execution runs in one worker thread so the UI remains responsive, including
while a save/restore request waits for a response. Completed observations update
the screen after each command. Output from the current turn is applied when its
save/restore dialog finishes. This frontend does not add sound, timed input,
mouse input to stories, or otherwise extend the interpreter's execution scope.

## Simple player and pipes

```sh
fernz --simple path/to/story.z3
printf 'look\ninventory\n' | fernz --simple path/to/story.z3
```

The simple player prints raw text immediately, including prompts before a
save/restore filename request. It reads lines until the story quits or stdin
reaches EOF. The terminal handles interactive input echo; redirected input is
not echoed. Window contents appear in execution order, without applying cursor
operations, styles or screen clearing. Use `--simple` for redirected input even
when Textual is installed.

## Screen size

Both frontends accept independent `--screen-width` and `--screen-height`
overrides. Width must be 1–255 and height 1–254.

The Textual player measures unspecified dimensions once, after laying out its
header, status line, command field and footer, before the game starts. It uses
the remaining game area, reserving a stable gutter for the lower window's
vertical history scrollbar. If an explicit width requires horizontal scrolling,
it also subtracts the shared horizontal scrollbar's height. A height override
that requires vertical scrolling similarly reduces the available width.
For example, a 116×40 terminal with the standard controls gives the game
114 columns and 34 rows. Very large measured sizes are capped at 255×254.

The simple player measures the terminal when its output is interactive; piped
output uses 80×25. Explicit overrides apply in either case. The library's
`FernzEnv` defaults remain 80×25, and inspection does not measure a terminal.

Resizing during play changes only the viewport, preserving the game's initial
geometry. Lower-window text wraps at the logical width; terminal resizing does
not reflow existing cells. Both windows scroll horizontally together when
necessary. The upper window never scrolls its contents in response to story
output. A quotation left behind by a contracting split becomes part of the
lower window and scrolls away naturally.

The frontend cell buffer and scrollback belong to the player, not the VM's
`GameState`. There are no changes to checkpoint formats or vector archives.

## Validation

Headless Textual tests exercise real synthetic stories, keyboard input, command
history, quit/error handling and storage dialogs. Rendering tests check window
overwrites, escaping, style isolation, wrapping and scrolling. The fast CI suite
installs the `textual` extra on Linux and the portable platform matrix. Base
installation checks still exercise the dependency-free wheel and fallback CLI.
