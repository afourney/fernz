"""Optional Textual player; the interpreter remains independent of this UI."""

from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
from typing import ClassVar

from rich.color import Color, ColorSystem
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen, Screen
from textual.scrollbar import ScrollBar, ScrollDown, ScrollTo, ScrollUp
from textual.strip import Strip
from textual.theme import Theme
from textual.widget import Widget
from textual.widgets import Button, Footer, Header, Input, Static

from ._cli_files import write_save
from ._env import FernzEnv
from ._errors import ExecutionError
from ._observation import Observation
from ._screen import ScreenBuffer

FERN_LOAM = Theme(
    name="fern-loam",
    primary="#496B45",
    secondary="#987A53",
    accent="#C4A45A",
    foreground="#E3DFCF",
    background="#101B14",
    surface="#243126",
    panel="#302A20",
    boost="#A3B485",
    warning="#D0AC5D",
    error="#CC7967",
    success="#86A871",
    dark=True,
)


# The xterm cube has no dark muted greens/browns: its first nonzero channel
# is 95. Use the grayscale ramp for dark surfaces and keep colour in accents,
# rather than letting RGB rounding turn those surfaces red, green or olive.
FERN_LOAM_256 = replace(
    FERN_LOAM,
    primary="#5F875F",
    secondary="#AF875F",
    accent="#AFAF5F",
    foreground="#DADADA",
    background="#121212",
    surface="#262626",
    panel="#303030",
    boost="#87AF87",
    warning="#D7AF5F",
    error="#AF5F5F",
    success="#87AF5F",
)


def _resolve_scrollbars(
    viewport: Widget,
    columns: int,
    rows: int,
    canvas_size: Callable[[int, int], tuple[int, int]],
) -> tuple[int, int, bool, bool]:
    """Return the canvas size and which scrollbars it needs within an area.

    Either scrollbar can require the other, so two follow-up passes resolve
    their space. canvas_size maps the space left by the bars to a canvas size.
    """
    horizontal = vertical = False
    for _ in range(3):
        available_columns = columns - (viewport.styles.scrollbar_size_vertical if vertical else 0)
        available_rows = rows - (viewport.styles.scrollbar_size_horizontal if horizontal else 0)
        width, height = canvas_size(available_columns, available_rows)
        horizontal = width > available_columns
        vertical = height > available_rows
    return width, height, horizontal, vertical


class PlayerScreen(Screen):
    """Paint unused space behind the opaque player and modal screens."""

    def render_line(self, y: int) -> Strip:
        """Use dark-shade cells without changing game or theme colours."""
        # Screen and the opaque game view resolve the same $background. Read
        # the computed CSS colour so runtime theme changes and theme defaults
        # are reflected without changing any VM-supplied cell colours.
        ink = self.styles.background.rich_color
        if self.app.console.color_system == "256":
            ink = ink.downgrade(ColorSystem.EIGHT_BIT)
        # Test the emitted colour: a nonblack RGB value can round to black in
        # the xterm palette. Keep the shade visible in that case as well.
        if ink.get_truecolor() == (0, 0, 0):
            ink = Color.parse("#303030")
        return Strip([Segment("▓" * self.size.width, Style(color=ink, bgcolor="#000000"))])


class FilePrompt(ModalScreen[str | None]):
    """Request a save/restore filename without blocking the event loop."""

    BINDINGS: ClassVar = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, operation: str) -> None:
        """Choose a label; the caller owns filesystem operations."""
        super().__init__()
        self.operation = operation

    def compose(self) -> ComposeResult:
        """Show a path field and explicit accept/cancel buttons."""
        with Vertical(id="dialog"):
            yield Static(f"{self.operation} game", classes="dialog-title")
            yield Input(placeholder="Saved-game path (blank cancels)", id="file-path")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button(self.operation, id="accept", variant="primary")

    def on_mount(self) -> None:
        """Focus the filename as soon as the dialog is ready."""
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Accept typed paths, including spaces, on Enter."""
        self.dismiss(event.value.strip() or None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Accept the path or cancel without touching a file."""
        value = self.query_one(Input).value.strip() if event.button.id == "accept" else ""
        self.dismiss(value or None)

    def action_cancel(self) -> None:
        """Report cancellation to the suspended story opcode."""
        self.dismiss(None)


class ConfirmOverwrite(ModalScreen[bool]):
    """Require an explicit confirmation before replacing an existing file."""

    BINDINGS: ClassVar = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, path: Path) -> None:
        """Retain the selected path as literal text."""
        super().__init__()
        self.path = path

    def compose(self) -> ComposeResult:
        """Show a safe default and a separately labelled replacement button."""
        with Vertical(id="dialog"):
            yield Static(Text(f"Replace existing save?\n{self.path}"))
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="cancel", variant="primary")
                yield Button("Replace", id="replace", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Only the Replace button authorizes the write."""
        self.dismiss(event.button.id == "replace")

    def action_cancel(self) -> None:
        """Leave the existing file untouched."""
        self.dismiss(False)


class ClippingWarning(ModalScreen[bool]):
    """Explain clipped game output without consuming a pending story input."""

    BINDINGS: ClassVar = [Binding("escape", "dismiss_once", "Dismiss", priority=True)]

    def __init__(self, width: int, height: int) -> None:
        """Describe the logical canvas, not the terminal viewport."""
        super().__init__()
        self.width, self.height = width, height

    def compose(self) -> ComposeResult:
        """Offer a one-time dismissal or session-only clipping suppression."""
        with Vertical(id="dialog"):
            yield Static("Game output does not fit", classes="dialog-title")
            yield Static(
                f"Some output was clipped outside the {self.width} x {self.height} game screen. "
                "Enlarging the terminal will not change this session's game dimensions. "
                "Relaunch with larger screen dimensions to display more game output.\n\n"
                "Mute warnings hides only these clipped-output warnings until you close Fernz.",
                id="clipping-message",
            )
            with Horizontal(classes="dialog-buttons"):
                yield Button("Dismiss", id="dismiss", variant="primary")
                yield Button("Mute warnings", id="mute")

    def on_mount(self) -> None:
        """Make Enter dismiss once by default."""
        self.query_one("#dismiss", Button).focus()

    def on_key(self, event: events.Key) -> None:
        """Never bubble dialog keys into the game's character-input handler."""
        if event.key in ("tab", "shift+tab"):
            return  # Let Textual move focus between the dialog buttons.
        event.stop()
        if event.key in ("enter", "space") and isinstance(self.app.focused, Button):
            event.prevent_default()
            self.app.focused.press()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Return only the warning preference, never a story input."""
        event.stop()
        self.dismiss(event.button.id == "mute")

    def action_dismiss_once(self) -> None:
        """Acknowledge this boundary without changing future warnings."""
        self.dismiss(False)


class HistoryBar(ScrollBar, can_focus=True):
    """Control lower-window history from the visible edge, outside the canvas."""

    BINDINGS: ClassVar = [
        Binding("up", "history('up')", show=False),
        Binding("down", "history('down')", show=False),
        Binding("pageup", "history('page_up')", show=False),
        Binding("pagedown", "history('page_down')", show=False),
        Binding("home", "history('home')", show=False),
        Binding("end", "history('end')", show=False),
    ]

    def __init__(self) -> None:
        """Reserve a stable, independently focusable history gutter."""
        super().__init__(thickness=2)
        self.styles.width = self.thickness
        self.id = "history-bar"
        self.tooltip = "Story history · Home/End, PageUp/PageDown (Alt+H / F6)"

    @property
    def history(self) -> ScrollableContainer:
        """Return the fixed lower window controlled by this scrollbar."""
        return self.app.query_one("#lower", ScrollableContainer)

    def action_history(self, direction: str) -> None:
        """Scroll history without changing the canvas pan or command draft."""
        getattr(self.history, f"scroll_{direction}")()

    def _on_scroll_to(self, message: ScrollTo) -> None:
        self.history.scroll_to(y=message.y, animate=message.animate)
        message.stop()

    def _on_scroll_up(self, event: ScrollUp) -> None:
        self.history.scroll_page_up()
        event.stop()

    def _on_scroll_down(self, event: ScrollDown) -> None:
        self.history.scroll_page_down()
        event.stop()

    def _on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self.history.scroll_up(animate=False)
        event.stop()

    def _on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self.history.scroll_down(animate=False)
        event.stop()

    async def _on_mouse_move(self, event: events.MouseMove) -> None:
        event.prevent_default()  # Do not also run ScrollBar's logical-height drag.
        # The track is viewport-sized, but the controlled window is game-sized.
        # Convert pointer travel using the visible track, not the logical height.
        if self.grabbed and self.size.height:
            self.history.scroll_to(
                y=self.grabbed_position
                + (event.screen_y - self.grabbed.y) * self.window_virtual_size / self.size.height,
                animate=False,
                immediate=True,
            )
        event.stop()


class RichCLI(App[int]):
    """Keep the UI responsive while a single worker owns VM execution."""

    TITLE = "Fernz"
    BINDINGS: ClassVar = [
        Binding("ctrl+q", "leave", "Quit", priority=True),
        Binding("ctrl+d", "leave", "Quit", show=False, priority=True),
        Binding("ctrl+c", "interrupt", "Interrupt", show=False, priority=True),
        Binding("alt+h,f6", "focus_history", "History", show=False, priority=True),
        Binding("alt+g,f7", "focus_canvas", "Canvas", show=False, priority=True),
        Binding("alt+i,f8", "focus_command", "Command", show=False, priority=True),
    ]
    CSS = """
    Screen { background: $background; color: $foreground; align: center middle; }
    #player { width: 100%; height: 100%; background: $background; overflow: hidden; }
    #game-row { height: 1fr; min-height: 0; overflow: hidden;
                scrollbar-color: $accent; }
    #history-bar { height: 1fr; }
    #history-bar:focus { background: $accent; }
    Header { background: $surface; color: $foreground; }
    #game-view { width: 1fr; height: 1fr; background: $background; }
    #game-screen { width: 0; height: 0; background: $background; }
    #upper { height: 0; display: none; background: $background; overflow: hidden; }
    #lower { height: 1fr; min-height: 0; background: $background;
             overflow-x: hidden; scrollbar-size-vertical: 0; }
    #upper-text, #lower-text { width: auto; height: auto; background: $background; color: $foreground; }
    #status { height: 1; color: $text-muted; background: $panel; }
    #command { background: $panel; color: $foreground; border: tall $primary; }
    #command:focus { border: tall $accent; }
    #command > .input--placeholder { color: $text-muted; }
    #command > .input--cursor { background: $accent; color: $background; }
    Footer { background: $surface; color: $foreground; }
    FooterKey > .footer-key--key { background: $primary; color: $foreground; }
    FooterKey > .footer-key--description { background: $surface; color: $foreground; }
    FilePrompt, ConfirmOverwrite, ClippingWarning {
        align: center middle; background: #00000088;
    }
    #dialog { width: 64; max-width: 95%; height: auto; padding: 1 2;
              border: round $accent; background: $surface; }
    .dialog-title { margin-bottom: 1; text-style: bold; }
    .dialog-buttons { height: auto; align-horizontal: right; margin-top: 1; }
    .dialog-buttons Button { margin-left: 1; }
    """

    def __init__(
        self,
        open_game: Callable[[int, int], FernzEnv],
        *,
        screen_width: int | None = None,
        screen_height: int | None = None,
    ) -> None:
        """Create the UI, deferring game creation until its viewport is measured."""
        super().__init__()
        self.open_game = open_game
        self.screen_width, self.screen_height = screen_width, screen_height
        self._load_error: OSError | ValueError | None = None
        self.register_theme(FERN_LOAM_256 if self.console.color_system == "256" else FERN_LOAM)
        self.theme = FERN_LOAM.name
        self.env: FernzEnv
        self.buffer = ScreenBuffer()
        self.busy = True
        self.character_input = False
        self.commands: list[str] = []
        self.history_position = 0
        self.draft = ""
        self._player_exit_code = 0
        self._player_closing = False
        self._dialog_result: Future | None = None
        self._game_size: tuple[int, int] | None = None
        self._clipping_warning_open = False
        self._mute_clipping_warnings = False

    def get_default_screen(self) -> Screen:
        """Keep the outer texture below all player widgets and dialogs."""
        return PlayerScreen(id="_default")

    def compose(self) -> ComposeResult:
        """Pan only the game; keep controls and history at the viewport edges."""
        with Vertical(id="player"):
            yield Header()
            with Horizontal(id="game-row"):
                with ScrollableContainer(id="game-view"), Vertical(id="game-screen"):
                    with ScrollableContainer(id="upper", can_focus=False):
                        yield Static(id="upper-text")
                    with ScrollableContainer(id="lower", can_focus=False):
                        yield Static(id="lower-text")
                yield HistoryBar()
            yield Static("Opening story…", id="status")
            yield Input(placeholder="Command", id="command", disabled=True)
            yield Footer()

    def run_repl(self) -> int:
        """Enter the application; main closes the environment created at startup."""
        result = self.run() or 0
        if self._load_error is not None:
            raise self._load_error
        return result

    def on_mount(self) -> None:
        """Wait for actual header, controls and viewport layout before measuring."""
        self.call_after_refresh(self._open_story)

    def _open_story(self) -> None:
        viewport = self.query_one("#game-view", ScrollableContainer)
        lower = self.query_one("#lower", ScrollableContainer)
        area = viewport.content_size
        # The separately laid-out history gutter is already outside this area.
        # Reserve canvas bars too, without reducing any configured dimension.
        # Recompute only dimensions the user left automatic.
        width, height, _, _ = _resolve_scrollbars(
            viewport,
            area.width,
            area.height,
            lambda columns, rows: (
                self.screen_width if self.screen_width is not None else max(1, min(255, columns)),
                self.screen_height if self.screen_height is not None else max(1, min(254, rows)),
            ),
        )
        try:
            self.env = self.open_game(width, height)
        except (OSError, ValueError) as error:
            self._load_error = error
            self.exit(2)
            return
        self.title = f"Fernz · {self.env.game_path.name}"
        # Follow through every layout pass (including screen splits and resizes).
        # Textual releases this anchor on user scrolling and restores it when
        # the user returns to the bottom; output refreshes must not reset it.
        lower.anchor()
        self._game_size = (width, height)
        self._layout_player()
        for attribute in ("scroll_y", "virtual_size"):
            self.watch(lower, attribute, self._sync_history)
        for selector in ("Header", "#status", "#command", "Footer"):
            self.watch(self.query_one(selector), "virtual_size", self._layout_player)
        self._advance(None)

    def on_resize(self) -> None:
        """Recenter the shell while preserving the VM's initial geometry."""
        self.call_after_refresh(self._layout_player)

    def _layout_player(self) -> None:
        if self._game_size is None:
            return
        width, height = self._game_size
        viewport = self.screen_stack[0].query_one("#game-view")
        history = self.screen_stack[0].query_one(HistoryBar)
        controls = sum(
            self.screen_stack[0].query_one(selector).outer_size.height
            for selector in ("Header", "#status", "#command", "Footer")
        )
        available = self.size
        # Hidden bars may not have a compositor size yet; their reserved rail
        # must still count in the preferred shell width.
        gutter = history.thickness
        # Start without bars on each resize so they also disappear when the
        # canvas fits again.
        _, _, horizontal, vertical = _resolve_scrollbars(
            viewport,
            available.width - gutter,
            available.height - controls,
            lambda columns, rows: (width, height),
        )
        # Use the resolved pair explicitly: Textual's automatic bars can retain
        # the previous pair during a cross-axis overflow/resize cycle.
        viewport.styles.overflow_x = "scroll" if horizontal else "hidden"
        viewport.styles.overflow_y = "scroll" if vertical else "hidden"
        # Hidden overflow disables ordinary scroll actions. Clear obsolete pan
        # offsets explicitly when an axis fits again, before centering it.
        viewport.scroll_to(
            x=None if horizontal else 0,
            y=None if vertical else 0,
            force=True,
            animate=False,
            immediate=True,
        )
        shell = self.screen_stack[0].query_one("#player")
        shell.styles.width = min(
            available.width,
            width + gutter + (viewport.styles.scrollbar_size_vertical if vertical else 0),
        )
        shell.styles.height = min(
            available.height,
            height + controls + (viewport.styles.scrollbar_size_horizontal if horizontal else 0),
        )

    def _sync_history(self) -> None:
        lower = self.screen_stack[0].query_one("#lower", ScrollableContainer)
        bar = self.screen_stack[0].query_one(HistoryBar)
        bar.window_virtual_size = lower.virtual_size.height
        bar.window_size = lower.scrollable_content_region.height
        bar.position = lower.scroll_y
        bar.styles.visibility = "visible" if lower.display and lower.max_scroll_y else "hidden"

    def action_focus_history(self) -> None:
        """Reach story history without panning to its logical right edge."""
        if len(self.screen_stack) == 1:
            self.query_one(HistoryBar).focus(scroll_visible=False)

    def action_focus_canvas(self) -> None:
        """Reach the shared canvas's keyboard panning controls."""
        if len(self.screen_stack) == 1:
            self.query_one("#game-view").focus(scroll_visible=False)

    def action_focus_command(self) -> None:
        """Return to the pinned command field without changing either scroll."""
        if len(self.screen_stack) == 1:
            self.query_one("#command").focus(scroll_visible=False)

    @work(thread=True)
    def _advance(self, action: str | None) -> None:
        """Run one bounded VM operation without blocking Textual's event loop."""
        try:
            response = self.env.reset() if action is None else self.env.step(action)
        except (NotImplementedError, ExecutionError, ValueError) as error:
            if not self._player_closing:
                self.call_from_thread(self._failed, str(error))
        else:
            if not self._player_closing:
                self.call_from_thread(self._received, response[0], response[-1])

    def _received(self, observation: Observation, info: dict[str, object]) -> None:
        self.buffer.apply(observation.stream)
        self._refresh_screen()
        self.sub_title = " · ".join(f"{key.capitalize()}: {value}" for key, value in info.items())
        self.busy = False
        if observation.diagnostics and not self._mute_clipping_warnings:
            self._clipping_warning_open = True
            self.query_one("#command", Input).disabled = True
            self.push_screen(
                ClippingWarning(self.buffer.width, self.buffer.height), self._clipping_dismissed
            )
            return
        self._resume_input()

    def _clipping_dismissed(self, mute: bool | None) -> None:
        self._clipping_warning_open = False
        self._mute_clipping_warnings |= bool(mute)
        if not self._player_closing:
            self._resume_input()

    def _resume_input(self) -> None:
        """Restore the pending input mode without advancing the story."""
        self.character_input = self.env.awaiting_character
        command = self.query_one("#command", Input)
        command.disabled = self.env.done or self.character_input
        if self.env.done:
            status = "Story ended · Ctrl+Q to exit"
        elif self.character_input:
            status = "Press a key · Enter to continue · Ctrl+Q to exit"
            self.set_focus(None)
        else:
            status = "↑/↓ command history · Scroll to review output · Ctrl+Q to exit"
            command.focus()
        self.query_one("#status", Static).update(status)

    def _refresh_screen(self) -> None:
        upper = self.query_one("#upper", ScrollableContainer)
        lower = self.query_one("#lower", ScrollableContainer)
        screen = self.query_one("#game-screen")
        self._game_size = (self.buffer.width, self.buffer.height)
        self._layout_player()
        screen.styles.width = self.buffer.width
        screen.styles.height = self.buffer.height
        upper.display = self.buffer.split > 0
        upper.styles.height = self.buffer.split
        lower.display = self.buffer.split < self.buffer.height
        self.query_one("#upper-text", Static).update(self.buffer.render(1))
        self.query_one("#lower-text", Static).update(self.buffer.render(0))
        self.call_after_refresh(self._sync_history)

    def _failed(self, message: str) -> None:
        self._player_exit_code = 1
        self.busy = False
        self.character_input = False
        self.query_one("#command", Input).disabled = True
        self.query_one("#status", Static).update(Text(f"{message} · Ctrl+Q to exit"))
        self.notify(message, title="Execution stopped", severity="error", timeout=10)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Echo a line once, remember it, and advance the story."""
        if event.input.id != "command" or self.busy or self._clipping_warning_open:
            return
        event.stop()
        action = event.value
        event.input.value = ""
        if action and (not self.commands or action != self.commands[-1]):
            self.commands.append(action)
        self.history_position = len(self.commands)
        self.draft = ""
        self.buffer.write(action)
        self._refresh_screen()
        self._submit(action)

    def _submit(self, action: str) -> None:
        if self._clipping_warning_open:
            return
        self.busy = True
        self.query_one("#command", Input).disabled = True
        self.query_one("#status", Static).update("Working…")
        self._advance(action)

    def on_key(self, event: events.Key) -> None:
        """Support single-key reads and preserve an unfinished history draft."""
        if (
            self.busy
            or self._clipping_warning_open
            or self._player_closing
            or len(self.screen_stack) != 1
            or self.env.done
        ):
            return
        if self.character_input:
            if event.key == "enter" or (event.character and event.character.isprintable()):
                event.stop()
                event.prevent_default()
                self._submit("" if event.key == "enter" else event.character or "")
        elif event.key in ("up", "down") and self.focused is self.query_one("#command"):
            event.stop()
            event.prevent_default()
            command = self.query_one("#command", Input)
            if self.history_position == len(self.commands):
                self.draft = command.value
            self.history_position = max(
                0, min(len(self.commands), self.history_position + (-1 if event.key == "up" else 1))
            )
            command.value = (
                self.commands[self.history_position]
                if self.history_position < len(self.commands)
                else self.draft
            )
            command.cursor_position = len(command.value)

    def _ask(self, screen: ModalScreen):
        result: Future = Future()

        def show() -> None:
            if self._player_closing:
                result.set_result(None)
                return
            self._dialog_result = result

            def complete(value) -> None:
                if not result.done():
                    result.set_result(value)
                self._dialog_result = None

            self.push_screen(screen, complete)

        self.call_from_thread(show)
        return result.result()

    def save(self, data: bytes) -> bool:
        """Ask for a path and atomically save after explicit overwrite consent."""
        name = self._ask(FilePrompt("Save"))
        if not name or self._player_closing:
            return False
        try:
            path = Path(name).expanduser()
            if path.exists() and not self._ask(ConfirmOverwrite(path)):
                return False
            if self._player_closing:
                return False
            write_save(path, data)
            return True
        except OSError as error:
            self.call_from_thread(self.notify, str(error), severity="error")
            return False

    def restore(self) -> bytes | None:
        """Read a user-selected saved game; errors return control to the story."""
        name = self._ask(FilePrompt("Restore"))
        if not name or self._player_closing:
            return None
        try:
            return Path(name).expanduser().read_bytes()
        except OSError as error:
            self.call_from_thread(self.notify, str(error), severity="error")
            return None

    def _release_dialog(self) -> None:
        self._player_closing = True
        if self._dialog_result is not None and not self._dialog_result.done():
            self._dialog_result.set_result(None)

    def action_leave(self) -> None:
        """Exit, cancelling any storage request still waiting for a response."""
        self._release_dialog()
        self.exit(self._player_exit_code)

    def action_interrupt(self) -> None:
        """Report the conventional interrupt status without a traceback."""
        self._player_exit_code = 130
        self.action_leave()

    def on_unmount(self) -> None:
        """Unblock a storage callback even when the terminal closes externally."""
        self._release_dialog()
