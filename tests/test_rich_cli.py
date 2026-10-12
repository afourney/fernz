import asyncio

import pytest

pytest.importorskip("textual")

from textual import events
from textual.widgets import Input

from fernz import FernzEnv
from fernz._rich_cli import ConfirmOverwrite, FilePrompt, RichCLI

from .save_story import save_story
from .story_files import READ, program_bytes


def player(tmp_path, code, version=3, *, width=80, height=25, app_type=RichCLI):
    game = tmp_path / "interactive story.z3"
    game.write_bytes(program_bytes(code, version=version))

    def open_game(columns, rows):
        return FernzEnv(
            game,
            save_handler=app.save,
            restore_handler=app.restore,
            screen_width=columns,
            screen_height=rows,
        )

    app = app_type(open_game, screen_width=width, screen_height=height)
    return app


async def settled(app, pilot):
    async with asyncio.timeout(5):
        while app.busy:
            await pilot.pause(0.01)
    await asyncio.wait_for(app.workers.wait_for_complete(), timeout=5)
    await pilot.pause()


async def dialog(app, pilot, kind=FilePrompt):
    async with asyncio.timeout(5):
        while not isinstance(app.screen, kind):
            await pilot.pause(0.01)
    await pilot.pause()


def test_rich_opening_commands_echo_and_history(tmp_path):
    # A prompt, three reads, and a final output byte before quitting.
    app = player(tmp_path, bytes.fromhex("e5 7f 3e") + READ * 3 + bytes.fromhex("e5 7f 21 ba"))

    async def run():
        async with app.run_test(size=(100, 40)) as pilot:
            await settled(app, pilot)
            command = app.query_one("#command", Input)
            assert command.has_focus
            assert app.buffer.render(0).plain.rstrip().endswith(">")
            command.value = "look"
            await pilot.press("enter")
            await settled(app, pilot)
            command.value = "inventory"
            await pilot.press("enter")
            await settled(app, pilot)
            command.value = "unfinished"
            await pilot.press("up")
            assert command.value == "inventory"
            await pilot.press("up")
            assert command.value == "look"
            await pilot.press("down", "down")
            assert command.value == "unfinished"
            await pilot.press("enter")
            await settled(app, pilot)
            text = app.buffer.render(0).plain
            assert text.count("look") == text.count("inventory") == 1
            assert text.rstrip().endswith("!")
            assert app.env.done and command.disabled
            await pilot.press("ctrl+q")
        assert app.return_value == 0

    asyncio.run(run())


@pytest.mark.parametrize("key,expected", [("A", "A"), ("enter", "\n")])
@pytest.mark.parametrize("version", (4, 5))
def test_character_input_needs_no_line_submission(tmp_path, key, expected, version):
    # read_char 1 -> global 16, print_char global 16, quit.
    app = player(tmp_path, bytes.fromhex("f6 7f 01 10 e5 bf 10 ba"), version=version)

    async def run():
        async with app.run_test() as pilot:
            await settled(app, pilot)
            assert app.character_input
            await pilot.press(key)
            await settled(app, pilot)
            assert app.env.done
            if expected != "\n":
                assert app.buffer.render(0).plain.strip() == expected
            else:
                row = app.buffer.height - 1 if version == 4 else 1
                assert app.buffer.cursors[0] == (row, 0)
            await pilot.press("ctrl+c")
        assert app.return_value == 130

    asyncio.run(run())


@pytest.mark.parametrize("replace", [False, True])
def test_save_dialog_requires_explicit_overwrite(tmp_path, replace):
    app = player(tmp_path, bytes.fromhex("b5 c6 e5 7f 46 ba e5 7f 53 ba"))
    path = tmp_path / "saved game.qzl"
    path.write_bytes(b"original")

    async def run():
        async with app.run_test(size=(100, 40)) as pilot:
            await dialog(app, pilot)
            await pilot.resize_terminal(78, 25)
            await pilot.press("f6", "f7", "f8")
            assert app.screen.query_one(Input).has_focus
            await pilot.resize_terminal(126, 46)
            app.screen.query_one(Input).value = str(path)
            await pilot.press("enter")
            await dialog(app, pilot, ConfirmOverwrite)
            assert app.focused.id == "cancel"
            if replace:
                await pilot.click("#replace")
            else:
                await pilot.press("enter")
            await settled(app, pilot)
            assert app.env.done
            assert app.buffer.render(0).plain.rstrip().endswith("S" if replace else "F")
        if replace:
            assert path.read_bytes()[8:12] == b"IFZS"
        else:
            assert path.read_bytes() == b"original"
        assert not list(tmp_path.glob(".saved game.qzl.*"))

    asyncio.run(run())


@pytest.mark.parametrize("operation", ["save", "restore"])
def test_storage_dialog_cancellation_continues_the_story(tmp_path, operation):
    opcode = "b5" if operation == "save" else "b6"
    app = player(tmp_path, bytes.fromhex(f"{opcode} c6 e5 7f 46 ba e5 7f 53 ba"))

    async def run():
        async with app.run_test() as pilot:
            await dialog(app, pilot)
            await pilot.press("enter" if operation == "save" else "escape")
            await settled(app, pilot)
            assert app.env.done
            assert app.buffer.render(0).plain.rstrip().endswith("F")

    asyncio.run(run())


def test_quitting_during_storage_unblocks_the_vm(tmp_path):
    app = player(tmp_path, bytes.fromhex("b5 c6 e5 7f 46 ba e5 7f 53 ba"))

    async def run():
        async with app.run_test() as pilot:
            await dialog(app, pilot)
            await pilot.press("ctrl+q")
            await asyncio.wait_for(app.workers.wait_for_complete(), timeout=5)
        assert app.return_value == 0

    asyncio.run(run())


@pytest.mark.parametrize("missing", [False, True])
def test_restore_resumes_a_real_save_or_reports_failure_to_story(tmp_path, missing):
    app = player(tmp_path, b"\xba")
    game = tmp_path / "interactive story.z3"
    game.write_bytes(save_story())
    path = tmp_path / "saved game.qzl"
    if not missing:

        def save(data):
            path.write_bytes(data)
            return True

        source = FernzEnv(game, save_handler=save)
        try:
            source.reset()
            source.step("save")
        finally:
            source.close()

    async def run():
        async with app.run_test() as pilot:
            await settled(app, pilot)
            app.query_one("#command", Input).value = "restore"
            await pilot.press("enter")
            await dialog(app, pilot)
            await pilot.resize_terminal(78, 25)
            await pilot.press("f6", "f7", "f8")
            assert app.screen.query_one(Input).has_focus
            await pilot.resize_terminal(126, 46)
            app.screen.query_one(Input).value = str(path)
            await pilot.press("enter")
            await settled(app, pilot)
            text = app.buffer.render(0).plain
            assert ("R=7" in text) is not missing
            assert app._player_exit_code == 0
            assert app.query_one("#command", Input).has_focus
            assert (app.env.screen_width, app.env.screen_height) == (80, 25)
            assert (app.buffer.width, app.buffer.height) == (80, 25)
            assert app.query_one("#game-screen").size == (80, 25)

    asyncio.run(run())


def test_execution_failure_stays_visible_and_exits_nonzero(tmp_path):
    app = player(tmp_path, b"\xb0")

    async def run():
        async with app.run_test() as pilot:
            await settled(app, pilot)
            assert app.query_one("#command", Input).disabled
            await pilot.press("ctrl+q")
        assert app.return_value == 1

    asyncio.run(run())


@pytest.mark.parametrize("split", [0, 1])
@pytest.mark.parametrize("logical_width", [80, 120])
def test_live_rows_keep_coordinates_across_terminal_resizes(tmp_path, split, logical_width):
    app = player(tmp_path, READ)

    async def run():
        async with app.run_test(size=(80, 24)) as pilot:
            await settled(app, pilot)
            app.buffer.apply(
                f"<reset><size {logical_width} 25><split {split}>"
                f"<top>UPPER<at 1 {logical_width - 3}><invert>HEAD<normal><bottom>"
                f"<at {split + 1} 1>LOWER<at {split + 1} {logical_width - 3}><bold>TAIL"
            )
            app._refresh_screen()
            logical = app.buffer.render(0)
            state = app.env.get_state()
            view = app.query_one("#game-view")
            lower = app.query_one("#lower")
            text = app.query_one("#lower-text")
            for size in [(80, 24), (116, 41), (60, 24), (80, 24)]:
                await pilot.resize_terminal(*size)
                await rendered(app, pilot)
                view.scroll_home(animate=False, immediate=True)
                lower.scroll_home(animate=False, immediate=True)
                await rendered(app, pilot)
                assert text.size.width == logical_width
                assert text.size.height == 25 - split
                assert lower.scrollable_content_region.width == logical_width
                assert "LOWER" in visible_game(app)
                assert not lower.show_horizontal_scrollbar
                # Both windows share one horizontal scrollbar, below the game.
                assert not app.query_one("#upper").show_horizontal_scrollbar
                view.scroll_to(x=view.max_scroll_x, animate=False, immediate=True)
                await rendered(app, pilot)
                assert "TAIL" in visible_game(app)
                if split:
                    assert "HEAD" in visible_game(app)
                    assert app.query_one("#upper").region.bottom == lower.region.y
                tail = text.render_line(0).crop(logical_width - 4, logical_width)
                assert tail.text == "TAIL"
                assert all(segment.style.bold for segment in tail)
                assert app.buffer.render(0) == logical
                assert app.env.get_state() == state
            await pilot.press("ctrl+q")

    asyncio.run(run())


def visible_game(app):
    viewport = app.query_one("#game-view").scrollable_content_region
    return "\n".join(
        strip.crop(viewport.x, viewport.right).text
        for strip in app.screen._compositor.render_strips()[viewport.y : viewport.bottom]
    )


def visible_lower(app):
    viewport = app.query_one("#lower").scrollable_content_region.intersection(
        app.query_one("#game-view").scrollable_content_region
    )
    return "\n".join(
        strip.crop(viewport.x, viewport.right).text
        for strip in app.screen._compositor.render_strips()[viewport.y : viewport.bottom]
    )


async def rendered(app, pilot):
    # pause() drains messages already queued, but layout can post more messages.
    # Cross a completed refresh before reading compositor geometry or scrolling.
    await pilot.pause()
    complete = asyncio.Event()
    app.call_after_refresh(complete.set)
    await asyncio.wait_for(complete.wait(), timeout=1)
    await pilot.pause()


async def scrolled(app, pilot):
    # Textual starts a deferred scroll after refresh. Waiting on the animator
    # before that refresh can return while the scroll is still only queued.
    await rendered(app, pilot)
    await asyncio.wait_for(pilot.wait_for_scheduled_animations(), timeout=5)
    await rendered(app, pilot)


@pytest.mark.parametrize("split", [1, 3, 20])
@pytest.mark.parametrize("initial_size", [(110, 40), (80, 24)])
def test_upper_rows_remain_accessible_across_resizes_and_input(tmp_path, split, initial_size):
    app = player(tmp_path, (READ + b"\x10") * 3, version=8, width=100, height=30)

    async def run():
        async with app.run_test(size=initial_size) as pilot:
            await settled(app, pilot)
            app.buffer.apply(
                f"<split {split}><top>"
                + "".join(
                    f"<at {row} 1><invert>ROW{row:02}<normal><at {row} 96>END{row:02}"
                    for row in range(1, split + 1)
                )
                + f"<bottom><at {split + 1} 1>"
            )
            app._refresh_screen()
            logical = app.buffer.render(1)
            state = app.env.get_state()
            view = app.query_one("#game-view")
            upper = app.query_one("#upper")
            lower = app.query_one("#lower")
            command = app.query_one("#command", Input)
            for size in [initial_size, (80, 24), (110, 40), initial_size]:
                await pilot.resize_terminal(*size)
                await rendered(app, pilot)
                view.scroll_home(animate=False, immediate=True)
                await rendered(app, pilot)
                assert upper.region.bottom == lower.region.y
                assert upper.size.height == split
                assert lower.size.height == 30 - split
                assert not upper.show_horizontal_scrollbar
                assert not upper.show_vertical_scrollbar
                assert "ROW01" in visible_game(app)
                assert view.show_horizontal_scrollbar == (size[0] < 102)
                if view.show_horizontal_scrollbar:
                    view.focus()
                    await pilot.press("ctrl+pagedown")
                    await scrolled(app, pilot)
                    assert view.scroll_x == view.max_scroll_x > 0
                    assert "END01" in visible_game(app)
                    # Wheel navigation is applied to the shared game viewport.
                    view.post_message(
                        events.MouseScrollLeft(view, 1, 1, 0, 0, 0, False, False, False)
                    )
                    await scrolled(app, pilot)
                    assert view.scroll_x < view.max_scroll_x
                if split == 20:
                    view.scroll_to(x=0, animate=False, immediate=True)
                    view.scroll_end(animate=False, immediate=True, x_axis=False)
                    await rendered(app, pilot)
                    assert "ROW20" in visible_game(app)
                assert app.buffer.render(1) == logical
                assert app.env.get_state() == state
            command.focus()
            command.value = "inventory"
            await pilot.press("enter")
            await settled(app, pilot)
            assert command.has_focus and not command.disabled
            assert "inventory" in app.buffer.render(0).plain
            await pilot.press("ctrl+q")

    asyncio.run(run())


@pytest.mark.parametrize("text", ["", "<at 1 1>LABEL"])
def test_split_preserves_blank_rows_and_stable_shared_scrollbar_geometry(tmp_path, text):
    app = player(tmp_path, READ * 3)

    async def run():
        async with app.run_test(size=(110, 40)) as pilot:
            await settled(app, pilot)
            upper = app.query_one("#upper")
            lower = app.query_one("#lower")
            view = app.query_one("#game-view")
            for split in (0, 1, 3, 20, 30, 3, 1, 0):
                app.buffer.apply(f"<reset><size 100 30><split {split}><top>{text}<bottom>")
                app._refresh_screen()
                logical = app.buffer.render(1)
                for size in [(110, 40), (102, 36), (100, 24), (80, 24), (110, 40)]:
                    await pilot.resize_terminal(*size)
                    await rendered(app, pilot)
                    geometry = (upper.region, lower.region, view.scrollbars_enabled)
                    await rendered(app, pilot)
                    assert (upper.region, lower.region, view.scrollbars_enabled) == geometry
                    assert upper.display == bool(split)
                    assert lower.display == (split < 30)
                    assert not app.query_one("#history-bar").visible
                    if split:
                        assert upper.size.height == split
                    if split < 30:
                        assert lower.size.height == 30 - split
                    if 0 < split < 30:
                        assert upper.region.bottom == lower.region.y
                    assert not upper.show_horizontal_scrollbar
                    assert not lower.show_horizontal_scrollbar
                    assert app.buffer.render(1) == logical
            await pilot.press("ctrl+q")

    asyncio.run(run())


async def following(app, pilot):
    # Worker completion and a single pause need not exhaust layout messages
    # posted by the previous frame. Bound the wait so a stuck viewport fails.
    await rendered(app, pilot)
    pane = app.query_one("#lower")
    async with asyncio.timeout(1):
        while pane.scroll_y != pane.max_scroll_y:
            await pilot.pause(0.01)
    await rendered(app, pilot)


def test_live_output_follows_late_layout_and_resizes(tmp_path):
    app = player(tmp_path, READ)

    async def run():
        async with app.run_test(size=(80, 24)) as pilot:
            await settled(app, pilot)
            pane = app.query_one("#lower")
            app.buffer.write(("word " * 15 + "\n") * 40 + "LATEST>")
            app._refresh_screen()
            await rendered(app, pilot)
            assert pane.scroll_y == pane.max_scroll_y > 0
            app.query_one("#game-view").scroll_end(animate=False, immediate=True, x_axis=False)
            await rendered(app, pilot)
            assert "LATEST>" in visible_lower(app)
            # A subsequent layout pass can happen after scroll_end's callback.
            # Only the visible viewport changes; pan to the last logical row.
            for size in [(64, 24), (110, 34), (80, 24)]:
                await pilot.resize_terminal(*size)
                await rendered(app, pilot)
                assert pane.scroll_y == pane.max_scroll_y
                app.query_one("#game-view").scroll_end(animate=False, immediate=True, x_axis=False)
                await rendered(app, pilot)
                assert "LATEST>" in visible_lower(app)
            # Changing the pinned window also reduces the transcript viewport.
            app.buffer.apply("<split 5>")
            app._refresh_screen()
            await rendered(app, pilot)
            assert pane.scroll_y == pane.max_scroll_y
            assert "LATEST>" in visible_lower(app)

    asyncio.run(run())


def test_output_preserves_scrollback_and_resumes_at_bottom(tmp_path):
    app = player(tmp_path, READ)

    async def run():
        async with app.run_test(size=(80, 24)) as pilot:
            await settled(app, pilot)
            pane = app.query_one("#lower")
            app.buffer.write("history\n" * 60)
            app._refresh_screen()
            await rendered(app, pilot)
            # Use the scrolling API used by Textual's user scroll actions.
            pane.scroll_to(y=10, animate=False, immediate=True)
            assert pane.scroll_y == 10
            await rendered(app, pilot)
            before = visible_lower(app)
            app.buffer.write("new output\n" * 30 + "LATEST>")
            app._refresh_screen()
            await rendered(app, pilot)
            assert pane.scroll_y == 10
            assert visible_lower(app) == before
            await pilot.resize_terminal(64, 24)
            await rendered(app, pilot)
            assert pane.scroll_y == 10
            # Returning to the bottom via ordinary scrolling resumes following.
            pane.scroll_to(y=pane.max_scroll_y, animate=False, immediate=True)
            await rendered(app, pilot)
            app.buffer.write("\nmore output\n" * 30 + "RESUMED>")
            app._refresh_screen()
            await rendered(app, pilot)
            assert pane.scroll_y == pane.max_scroll_y
            app.query_one("#game-view").scroll_end(animate=False, immediate=True, x_axis=False)
            await rendered(app, pilot)
            assert "RESUMED>" in visible_lower(app)

    asyncio.run(run())


def test_repeated_commands_follow_long_responses(tmp_path):
    # print_char 'x', new_line, repeated past the viewport, then prompt/read.
    response = bytes.fromhex("e5 7f 78 bb") * 40 + bytes.fromhex("e5 7f 3e")
    app = player(tmp_path, (response + READ) * 9 + b"\xba")

    async def run():
        async with app.run_test(size=(80, 24)) as pilot:
            await settled(app, pilot)
            pane = app.query_one("#lower")
            command = app.query_one("#command", Input)
            for _ in range(7):
                await following(app, pilot)
                assert pane.scroll_y == pane.max_scroll_y > 0
                app.query_one("#game-view").scroll_end(animate=False, immediate=True, x_axis=False)
                await rendered(app, pilot)
                assert visible_lower(app).rstrip().endswith(">")
                assert command.has_focus and not command.disabled
                command.value = "look"
                await pilot.press("enter")
                await settled(app, pilot)
            await following(app, pilot)
            assert pane.scroll_y == pane.max_scroll_y
            assert visible_lower(app).rstrip().endswith(">")
            # A real wheel event releases following, even across command echo,
            # worker completion, and focus returning to the enabled input.
            pane.post_message(events.MouseScrollUp(pane, 1, 1, 0, 0, 0, False, False, False))
            await scrolled(app, pilot)
            position = pane.scroll_y
            assert position < pane.max_scroll_y
            command.value = "look"
            await pilot.press("enter")
            await settled(app, pilot)
            assert pane.scroll_y == position
            assert command.has_focus and not command.disabled

    asyncio.run(run())


@pytest.mark.parametrize("size", [(110, 36), (116, 41)])
def test_quote_survives_split_shrink_before_next_input(tmp_path, size):
    # V5: first read, expand upper window, position beyond the split (the
    # interpreter expands it implicitly), print a quote, shrink, then read.
    # This is a synthetic story, with no ROM or saved-game dependency.
    read = READ + b"\x10"
    quote = "Visiting hours: 7 to 6"
    code = (
        b"\xbb" * 30
        + read
        + bytes.fromhex("ea 7f 08 eb 7f 01 f1 7f 01 ef 5f 09 15")
        + b"".join(bytes((0xE5, 0x7F, ord(char))) for char in quote)
        + bytes.fromhex("f1 7f 00 eb 7f 00 ea 7f 01 bb e5 7f 3e")
        + read
        + b"\xba"
    )
    app = player(tmp_path, code, version=5)

    async def run():
        async with app.run_test(size=size) as pilot:
            await settled(app, pilot)
            command = app.query_one("#command", Input)
            command.value = "read sign"
            await pilot.press("enter")
            await settled(app, pilot)
            assert app.buffer.split == 1
            assert quote in visible_lower(app)
            assert visible_lower(app).rstrip().endswith(">")
            assert command.has_focus and not command.disabled
            assert not app.character_input

    asyncio.run(run())


@pytest.mark.parametrize("theme", ["fern-loam", "textual-dark", "textual-light", "nord"])
def test_themes_recolour_defaults_and_scrollback_but_preserve_story_colours(tmp_path, theme):
    from textual.color import Color

    app = player(tmp_path, READ)

    async def run():
        async with app.run_test(size=(110, 34)) as pilot:
            await settled(app, pilot)
            assert app.theme == "fern-loam"
            app.buffer.apply(
                "<reset><size 80 3>history\n<bold><italic><invert>A<normal><color white black>B<color red #123456>C<color default default>D"
            )
            app.buffer.write("\nline\nlast")
            app._refresh_screen()
            before = app.buffer.render(0)
            state = app.env.get_state()
            app.theme = theme
            await pilot.pause()
            text = app.query_one("#lower-text")
            variables = app.get_css_variables()
            foreground = Color.parse(variables["foreground"]).rich_color
            background = Color.parse(variables["background"]).rich_color
            segments = list(text.render_line(0))
            assert any(
                "history" in segment.text
                and segment.style.color == foreground
                and segment.style.bgcolor == background
                for segment in segments
            )
            segments = list(text.render_line(1))
            by_char = {
                char: segment.style
                for segment in segments
                for char in segment.text
                if char in "ABCD"
            }
            assert by_char["A"].bold and by_char["A"].italic and by_char["A"].reverse
            assert by_char["B"].color.get_truecolor() == (255, 255, 255)
            assert by_char["B"].bgcolor.get_truecolor() == (0, 0, 0)
            assert by_char["C"].color.get_truecolor() == (255, 0, 0)
            assert by_char["C"].bgcolor.get_truecolor() == (18, 52, 86)
            assert by_char["D"].color == foreground and by_char["D"].bgcolor == background
            assert app.buffer.render(0) == before
            assert app.env.get_state() == state
            command = app.query_one("#command", Input)
            assert command.has_focus
            assert command.styles.border_top[1] == Color.parse(variables["accent"])

    asyncio.run(run())


def test_fern_loam_uses_the_selected_palette_exactly():
    from fernz._rich_cli import FERN_LOAM

    expected = {
        "name": "fern-loam",
        "primary": "#496B45",
        "secondary": "#987A53",
        "accent": "#C4A45A",
        "foreground": "#E3DFCF",
        "background": "#101B14",
        "surface": "#243126",
        "panel": "#302A20",
        "boost": "#A3B485",
        "warning": "#D0AC5D",
        "error": "#CC7967",
        "success": "#86A871",
        "dark": True,
    }
    assert {key: getattr(FERN_LOAM, key) for key in expected} == expected


@pytest.mark.parametrize("system", ["truecolor", "256"])
def test_terminal_colour_depth_selects_theme_and_preserves_story_colours(
    tmp_path, monkeypatch, system
):
    from io import StringIO

    from rich.color import Color, ColorSystem
    from rich.console import Console
    from textual import constants

    from fernz._rich_cli import FERN_LOAM, FERN_LOAM_256

    monkeypatch.setattr(constants, "COLOR_SYSTEM", system)
    monkeypatch.delenv("NO_COLOR", raising=False)
    app = player(tmp_path, READ)
    assert app.current_theme == (FERN_LOAM_256 if system == "256" else FERN_LOAM)

    async def run():
        async with app.run_test(size=(110, 34)) as pilot:
            await settled(app, pilot)
            app.buffer.apply(
                "<reset><size 80 3>A<color red #123456><bold>B<color default default>C"
            )
            app._refresh_screen()
            await pilot.pause()
            row = list(app.query_one("#lower-text").render_line(0))
            styles = {
                char: segment.style for segment in row for char in segment.text if char in "ABC"
            }
            expected = app.current_theme
            assert styles["A"].color == Color.parse(expected.foreground)
            assert styles["A"].bgcolor == Color.parse(expected.background)
            assert styles["B"].color == Color.parse("#ff0000")
            assert styles["B"].bgcolor == Color.parse("#123456")
            assert styles["B"].bold
            assert styles["C"].color == styles["A"].color
            assert styles["C"].bgcolor == styles["A"].bgcolor
            if system == "256":
                # Verify actual emitted ANSI colours, not a true-colour SVG export.
                stream = StringIO()
                console = Console(
                    file=stream,
                    color_system="256",
                    force_terminal=True,
                    highlight=False,
                    markup=False,
                )
                for strip in app.screen._compositor.render_strips():
                    for segment in strip:
                        console.print(segment.text, style=segment.style, end="")
                ansi = stream.getvalue()
                for index in (233, 235, 236):
                    assert f"48;5;{index}" in ansi
                for index in (22, 52, 58):
                    assert f"48;5;{index}m" not in ansi
                assert "48;2;" not in ansi
                for field in ("primary", "secondary", "accent", "background", "surface", "panel"):
                    colour = Color.parse(getattr(expected, field))
                    assert colour.downgrade(ColorSystem.EIGHT_BIT).get_truecolor() == colour.triplet
            app.theme = "nord"
            await pilot.pause()
            assert app.current_theme.name == "nord"
            app.theme = "fern-loam"
            await pilot.pause()
            assert app.current_theme == expected

    asyncio.run(run())


@pytest.mark.parametrize(
    "size,width,height,expected,horizontal,vertical",
    [
        ((116, 40), None, None, (114, 34), False, False),
        ((80, 24), None, None, (78, 18), False, False),
        ((80, 24), 100, None, (100, 17), True, False),
        ((116, 40), None, 40, (112, 40), False, True),
        ((116, 40), 100, None, (100, 34), False, False),
        ((116, 40), None, 30, (114, 30), False, False),
        ((116, 40), 100, 30, (100, 30), False, False),
        ((80, 24), 100, 30, (100, 30), True, True),
        ((270, 265), None, None, (255, 254), False, False),
    ],
)
def test_startup_measures_game_area_and_scrollbars(
    tmp_path, size, width, height, expected, horizontal, vertical
):
    app = player(tmp_path, READ + b"\x10", version=5, width=width, height=height)

    async def run():
        async with app.run_test(size=size) as pilot:
            await settled(app, pilot)
            await rendered(app, pilot)
            view = app.query_one("#game-view")
            screen = app.query_one("#game-screen")
            lower = app.query_one("#lower")
            assert (app.env.screen_width, app.env.screen_height) == expected
            assert app.env.memory.read_byte(0x21) == expected[0]
            assert app.env.memory.read_byte(0x20) == expected[1]
            assert view.region.y == app.query_one("Header").region.bottom
            assert view.region.bottom == app.query_one("#status").region.y
            assert view.show_horizontal_scrollbar == horizontal
            assert view.show_vertical_scrollbar == vertical
            assert lower.scrollable_content_region.width == expected[0]
            assert screen.size.height == expected[1]
            # Growing history cannot cause a new horizontal scrollbar or change
            # the game's header dimensions; its gutter was reserved at startup.
            app.buffer.write("history\n" * (expected[1] + 5))
            app._refresh_screen()
            await rendered(app, pilot)
            assert lower.show_vertical_scrollbar
            assert view.show_horizontal_scrollbar == horizontal
            assert lower.scrollable_content_region.width == expected[0]
            state = app.env.get_state()
            await pilot.resize_terminal(90, 30)
            await rendered(app, pilot)
            assert app.env.get_state() == state
            assert (app.buffer.width, app.buffer.height) == expected
            await pilot.press("ctrl+q")

    asyncio.run(run())


def test_quote_and_second_status_row_stay_adjacent_with_history(tmp_path):
    def print_text(text):
        return b"".join(bytes((0xE5, 0x7F, ord(char))) for char in text)

    read = READ + b"\x10"
    code = (
        (print_text("old history") + b"\xbb") * 40
        + read
        + bytes.fromhex("ea 7f 02 eb 7f 01 ef 5f 01 01")
        + print_text("STATUS ONE")
        + bytes.fromhex("ef 5f 02 01")
        + print_text("STATUS TWO")
        + bytes.fromhex("eb 7f 00 ea 7f 0a eb 7f 01 ef 5f 05 04 f1 7f 01")
        + print_text("QUOTATION")
        + bytes.fromhex("f1 7f 00 eb 7f 00 ea 7f 01")
        + read
    )
    app = player(tmp_path, code, version=5, width=100, height=30)

    async def run():
        async with app.run_test(size=(116, 40)) as pilot:
            await settled(app, pilot)
            app.query_one("#command", Input).value = "quote"
            await pilot.press("enter")
            await settled(app, pilot)
            assert app.buffer.split == 1
            assert app.buffer.history
            lower = app.query_one("#lower")
            view = app.query_one("#game-view")
            for size in [(116, 40), (116, 36), (78, 25), (80, 40), (116, 34), (116, 40)]:
                await pilot.resize_terminal(*size)
                await rendered(app, pilot)
                view.scroll_home(animate=False, immediate=True)
                await rendered(app, pilot)
                rows = visible_game(app).splitlines()
                assert rows[0].startswith("STATUS ONE")
                assert rows[1].startswith("STATUS TWO")
                assert rows[4][3:].startswith("QUOTATION")
                if size == (116, 40):
                    assert all(not row.strip() for row in rows[30:])
                assert lower.scroll_y == lower.max_scroll_y
            # History is still available, and returning to live output restores
            # the exact physical row relationship without changing any cells.
            lower.scroll_home(animate=False, immediate=True)
            await rendered(app, pilot)
            assert "old history" in visible_lower(app)
            lower.scroll_end(animate=False, immediate=True)
            await rendered(app, pilot)
            assert visible_game(app).splitlines()[1].startswith("STATUS TWO")
            await pilot.press("ctrl+q")

    asyncio.run(run())


@pytest.mark.parametrize("width", [None, 130])
def test_automatic_size_uses_actual_control_layout(tmp_path, width):
    class TallControls(RichCLI):
        CSS = (
            RichCLI.CSS
            + "Header {height: 2;} #status {height: 2;} #command {height: 4;} Footer {height: 2;}"
        )

    app = player(tmp_path, READ, width=width, height=None, app_type=TallControls)

    async def run():
        async with app.run_test(size=(120, 50)) as pilot:
            await settled(app, pilot)
            await rendered(app, pilot)
            controls = sum(
                app.query_one(selector).region.height
                for selector in ("Header", "#status", "#command", "Footer")
            )
            assert controls == 10  # Includes the input field's borders.
            view = app.query_one("#game-view")
            assert view.size.height == 50 - controls
            assert app.env.screen_height == 50 - controls - int(width is not None)
            assert app.env.screen_width == (118 if width is None else width)
            await pilot.press("ctrl+q")

    asyncio.run(run())


@pytest.mark.parametrize("error", [FileNotFoundError("missing story"), ValueError("bad story")])
def test_deferred_load_failure_returns_to_cli_without_running_a_story(monkeypatch, error):
    def open_game(width, height):
        raise error

    app = RichCLI(open_game)

    async def run():
        async with app.run_test() as pilot:
            await pilot.pause()
        assert app.return_value == 2
        assert app._load_error is error
        assert not hasattr(app, "env")

    asyncio.run(run())
    monkeypatch.setattr(app, "run", lambda: app.return_value)
    with pytest.raises(type(error), match=str(error)):
        app.run_repl()


@pytest.mark.parametrize(
    "size,shell_size,bars",
    [
        ((102, 36), (102, 36), (False, False)),
        ((126, 46), (102, 36), (False, False)),
        ((78, 25), (78, 25), (True, True)),
        ((126, 27), (104, 27), (True, False)),
        ((78, 46), (78, 37), (False, True)),
        # An otherwise fitting axis overflows when the other needs a bar.
        ((102, 35), (102, 35), (True, True)),
        ((101, 36), (101, 36), (True, True)),
        ((104, 35), (104, 35), (True, False)),
        ((101, 37), (101, 37), (False, True)),
    ],
)
def test_fixed_canvas_centering_and_pinned_edges(tmp_path, size, shell_size, bars):
    app = player(tmp_path, (READ + b"\x10") * 3, version=5, width=100, height=30)

    async def run():
        async with app.run_test(size=(102, 36)) as pilot:
            await settled(app, pilot)
            await rendered(app, pilot)
            assert app.query_one("#player").size == (102, 36)
            assert app.query_one("#game-view").size == (100, 30)
            assert not app.query_one("#history-bar").visible
            app.buffer.apply("<split 2><top><invert>STATUS ONE<at 2 1>STATUS TWO<bottom>")
            app.buffer.write("history\n" * 60)
            app._refresh_screen()
            await rendered(app, pilot)
            view = app.query_one("#game-view")
            lower = app.query_one("#lower")
            bar = app.query_one("#history-bar")
            command = app.query_one("#command", Input)
            command.value = "unfinished draft"
            logical = (app.buffer.render(0), app.buffer.render(1))
            state = app.env.get_state()
            for terminal in (size, (102, 36), size, (126, 46), size):
                await pilot.resize_terminal(*terminal)
                await rendered(app, pilot)
                shell = app.query_one("#player")
                expected = shell_size if terminal == size else (102, 36)
                expected_bars = bars if terminal == size else (False, False)
                assert tuple(shell.region.size) == expected
                assert shell.region.x == (terminal[0] - expected[0]) // 2
                assert shell.region.y == (terminal[1] - expected[1]) // 2
                assert view.scrollbars_enabled == expected_bars
                assert app.query_one("#game-screen").size == (100, 30)
                assert app.query_one("#upper").size == (100, 2)
                assert lower.size == (100, 28)
                assert lower.scrollable_content_region.width == 100
                assert not lower.show_horizontal_scrollbar
                assert bar.visible
                assert bar.region.right == shell.region.right
                assert bar.window_size == 28
                assert bar.window_virtual_size == lower.virtual_size.height
                for scrollbar, visible in (
                    (view.vertical_scrollbar, expected_bars[0]),
                    (view.horizontal_scrollbar, expected_bars[1]),
                ):
                    assert scrollbar.display == visible
                    if visible:
                        assert view.region.contains_region(scrollbar.region)
                pinned = [app.query_one(s) for s in ("Header", "#status", "#command", "Footer")]
                regions = [w.region for w in pinned] + [bar.region]
                for x, y in ((0, 0), (view.max_scroll_x, view.max_scroll_y)):
                    view.scroll_to(x=x, y=y, animate=False, immediate=True)
                    await rendered(app, pilot)
                    assert [w.region for w in pinned] + [bar.region] == regions
                    for widget in pinned:
                        assert shell.region.contains_region(widget.region)
                        assert widget.region.width == shell.region.width
                    assert view.region.y == pinned[0].region.bottom
                    assert view.region.bottom == pinned[1].region.y
                    assert pinned[1].region.bottom == pinned[2].region.y
                    assert pinned[2].region.bottom == pinned[3].region.y
                assert command.has_focus and command.value == "unfinished draft"
                assert (app.buffer.render(0), app.buffer.render(1)) == logical
                assert app.env.get_state() == state
                assert lower.scroll_y == lower.max_scroll_y
                assert app.screen.styles.background == shell.styles.background
            await pilot.press("ctrl+q")

    asyncio.run(run())


@pytest.mark.parametrize("keys", [("f6", "f7", "f8"), ("alt+h", "alt+g", "alt+i")])
def test_pinned_history_mouse_keyboard_and_canvas_are_independent(tmp_path, keys):
    app = player(tmp_path, READ * 3, width=100, height=30)

    async def run():
        async with app.run_test(size=(78, 25)) as pilot:
            await settled(app, pilot)
            app.buffer.write("history\n" * 90)
            app._refresh_screen()
            await rendered(app, pilot)
            view = app.query_one("#game-view")
            lower = app.query_one("#lower")
            bar = app.query_one("#history-bar")
            command = app.query_one("#command", Input)
            assert view.scroll_y == 0  # No bottom anchor hiding status at startup.
            view.scroll_end(animate=False, immediate=True)
            await rendered(app, pilot)
            pan = view.scroll_offset
            pinned = bar.region
            command.value = "draft"
            state = app.env.get_state()
            assert all(
                not binding.show for binding in app.BINDINGS if binding.action.startswith("focus_")
            )
            await pilot.press(keys[0], "home")
            await scrolled(app, pilot)
            assert bar.has_focus and lower.scroll_y == 0
            assert view.scroll_offset == pan
            assert bar.position == 0
            # Click below the thumb, then drag from the top to the track bottom.
            assert await pilot.click(bar, offset=(0, bar.size.height - 1))
            await scrolled(app, pilot)
            assert 0 < lower.scroll_y <= lower.max_scroll_y
            await pilot.press("home")
            await scrolled(app, pilot)
            await pilot.mouse_down(bar, offset=(0, 0))
            await pilot.hover(bar, offset=(0, bar.size.height - 1))
            await pilot.mouse_up(bar, offset=(0, bar.size.height - 1))
            await scrolled(app, pilot)
            assert lower.scroll_y == lower.max_scroll_y
            assert bar.position == lower.scroll_y
            assert view.scroll_offset == pan and bar.region == pinned
            # Wheel events on the visible rail reach history even at the far pan.
            bar.post_message(events.MouseScrollUp(bar, 0, 1, 0, 0, 0, False, False, False))
            await scrolled(app, pilot)
            assert lower.scroll_y < lower.max_scroll_y
            position = lower.scroll_y
            await pilot.press(keys[1], "home", "ctrl+pageup")
            await scrolled(app, pilot)
            assert view.has_focus and view.scroll_offset == (0, 0)
            assert lower.scroll_y == position
            await pilot.press(keys[2])
            assert app.env.get_state() == state
            assert not app.commands
            assert command.has_focus and command.value == "draft"
            await pilot.press("enter")
            await settled(app, pilot)
            assert app.commands == ["draft"]
            assert command.has_focus and not command.disabled
            assert view.scroll_offset == (0, 0)
            assert lower.scroll_y == position

    asyncio.run(run())


@pytest.mark.parametrize("keys", [("f6", "f7", "f8"), ("alt+h", "alt+g", "alt+i")])
def test_single_key_input_after_panning_with_fixed_geometry(tmp_path, keys):
    app = player(
        tmp_path, bytes.fromhex("f6 7f 01 10 e5 bf 10 ba"), version=5, width=100, height=30
    )

    async def run():
        async with app.run_test(size=(78, 25)) as pilot:
            await settled(app, pilot)
            state = app.env.get_state()
            await pilot.press(*keys, keys[1], "end", "ctrl+pagedown")
            assert app.env.get_state() == state
            assert not app.commands
            await scrolled(app, pilot)
            assert app.character_input
            view = app.query_one("#game-view")
            assert view.scroll_offset == (view.max_scroll_x, view.max_scroll_y)
            await pilot.resize_terminal(126, 46)
            await rendered(app, pilot)
            await pilot.resize_terminal(78, 25)
            await rendered(app, pilot)
            await pilot.press("A")
            await settled(app, pilot)
            assert app.env.done
            assert app.buffer.render(0).plain.strip() == "A"
            assert (app.env.screen_width, app.env.screen_height) == (100, 30)
            assert app.query_one("#command", Input).disabled

    asyncio.run(run())


@pytest.mark.parametrize("system", ["truecolor", "256"])
def test_outer_texture_is_composited_behind_player_and_dialog(tmp_path, monkeypatch, system):
    from io import StringIO

    from rich.console import Console
    from textual import constants

    monkeypatch.setattr(constants, "COLOR_SYSTEM", system)
    monkeypatch.delenv("NO_COLOR", raising=False)
    app = player(tmp_path, READ, version=5, width=100, height=30)

    async def run():
        async with app.run_test(size=(102, 36)) as pilot:
            await settled(app, pilot)
            app.buffer.write("history\n" * 60)
            app._refresh_screen()
            logical = app.buffer.render(0)
            for size in ((126, 46), (102, 36), (78, 25), (126, 27), (78, 46), (126, 46)):
                await pilot.resize_terminal(*size)
                await rendered(app, pilot)
                shell = app.query_one("#player").region
                strips = app.screen._compositor.render_strips()
                for y, strip in enumerate(strips):
                    for x, char in enumerate(strip.text):
                        assert (char == "▓") == (not shell.contains(x, y))
                assert app.buffer.render(0) == logical
                if size == (126, 46):
                    stream = StringIO()
                    console = Console(file=stream, color_system=system, force_terminal=True)
                    for segment in strips[0]:
                        console.print(segment.text, style=segment.style, end="")
                    ansi = stream.getvalue()
                    assert "▓" in ansi
                    if system == "256":
                        assert "38;5;22" in ansi  # Darkest fixed xterm green, never rounded black.
                        assert "48;5;16" in ansi
                        assert "38;2;" not in ansi
                    else:
                        assert "38;2;16;48;32" in ansi
                        assert "48;2;0;0;0" in ansi
            app.push_screen(FilePrompt("Save"))
            await rendered(app, pilot)
            dialog_region = app.screen.query_one("#dialog").region
            for strip in app.screen._compositor.render_strips()[
                dialog_region.y : dialog_region.bottom
            ]:
                assert "▓" not in strip.crop(dialog_region.x, dialog_region.right).text
            await pilot.press("escape")
            await rendered(app, pilot)
            assert app.buffer.render(0) == logical

    asyncio.run(run())
