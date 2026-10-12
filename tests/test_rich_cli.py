import asyncio

import pytest

pytest.importorskip("textual")

from textual import events
from textual.widgets import Input

from fernz import FernzEnv
from fernz._rich_cli import ConfirmOverwrite, FilePrompt, RichCLI

from .save_story import save_story
from .story_files import READ, program_bytes


def player(tmp_path, code, version=3):
    game = tmp_path / "interactive story.z3"
    game.write_bytes(program_bytes(code, version=version))
    app = RichCLI()
    app.env = FernzEnv(game, save_handler=app.save, restore_handler=app.restore)
    return app


async def settled(app, pilot):
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
    game = app.env.game_path
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
    app.env = FernzEnv(game, save_handler=app.save, restore_handler=app.restore)

    async def run():
        async with app.run_test() as pilot:
            await settled(app, pilot)
            app.query_one("#command", Input).value = "restore"
            await pilot.press("enter")
            await dialog(app, pilot)
            app.screen.query_one(Input).value = str(path)
            await pilot.press("enter")
            await settled(app, pilot)
            text = app.buffer.render(0).plain
            assert ("R=7" in text) is not missing
            assert app._player_exit_code == 0
            assert app.query_one("#command", Input).has_focus

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
def test_lower_text_remains_visible_across_terminal_resizes(tmp_path, split, logical_width):
    app = player(tmp_path, READ)
    # Independent synthetic rows exercise both word wrapping and long-word folding.
    word_row = "word " * (logical_width // 5 - 1) + "EDGE!"
    long_row = "x" * (logical_width - 4) + "TAIL"

    async def run():
        async with app.run_test(size=(80, 24)) as pilot:
            await settled(app, pilot)
            app.buffer.apply(
                f"<reset><size {logical_width} 25><split {split}>"
                f"<top><at 1 {logical_width - 3}><invert>HEAD<at 1 1>UPPER<normal><bottom>"
                f"<at {split + 1} 1>{word_row}\n<bold>{long_row}"
            )
            app._refresh_screen()
            logical = app.buffer.render(0).plain
            state = app.env.get_state()
            for size in [(80, 24), (116, 41), (60, 24), (80, 24)]:
                await pilot.resize_terminal(*size)
                await pilot.pause()
                pane = app.query_one("#lower")
                text = app.query_one("#lower-text")
                pane.scroll_home(animate=False)
                await pilot.pause()
                viewport = pane.scrollable_content_region
                assert text.size.width == viewport.width
                assert pane.max_scroll_x == 0
                # Read the actual composited viewport, not the logical buffer.
                visible = "".join(
                    strip.crop(viewport.x, viewport.right).text
                    for strip in app.screen._compositor.render_strips()[
                        viewport.y : viewport.bottom
                    ]
                )
                assert "".join(visible.split()) == "".join((word_row + long_row).split())
                # Folding retains styles, and resizing never mutates logical cells or VM state.
                rendered_cells = [
                    (char, segment.style)
                    for row in range(text.size.height)
                    for segment in text.render_line(row)
                    for char in segment.text
                    if not char.isspace()
                ]
                # The tail itself may fold across two viewport rows.
                assert "".join(char for char, _ in rendered_cells[-4:]) == "TAIL"
                assert all(style.bold for _, style in rendered_cells[-4:])
                assert app.buffer.render(0).plain == logical
                assert app.env.get_state() == state
                if split:
                    upper = app.query_one("#upper-text")
                    assert upper.size.height == 1
                    assert upper.render_line(0).text == "UPPER" + " " * (logical_width - 9) + "HEAD"

    asyncio.run(run())


def visible_lower(app):
    viewport = app.query_one("#lower").scrollable_content_region
    return "\n".join(
        strip.crop(viewport.x, viewport.right).text
        for strip in app.screen._compositor.render_strips()[viewport.y : viewport.bottom]
    )


async def following(app, pilot):
    # Worker completion and a single pause need not exhaust layout messages
    # posted by the previous frame. Bound the wait so a stuck viewport fails.
    pane = app.query_one("#lower")
    async with asyncio.timeout(1):
        while pane.scroll_y != pane.max_scroll_y:
            await pilot.pause(0.01)


def test_live_output_follows_late_layout_and_resizes(tmp_path):
    app = player(tmp_path, READ)

    async def run():
        async with app.run_test(size=(80, 24)) as pilot:
            await settled(app, pilot)
            pane = app.query_one("#lower")
            app.buffer.write(("word " * 15 + "\n") * 40 + "LATEST>")
            app._refresh_screen()
            await pilot.pause()
            assert pane.scroll_y == pane.max_scroll_y > 0
            assert "LATEST>" in visible_lower(app)
            # A subsequent layout pass can happen after scroll_end's callback.
            # Wrapping and viewport height both change without another response.
            for size in [(64, 24), (110, 34), (80, 24)]:
                await pilot.resize_terminal(*size)
                await pilot.pause()
                assert pane.scroll_y == pane.max_scroll_y
                assert "LATEST>" in visible_lower(app)
            # Changing the pinned window also reduces the transcript viewport.
            app.buffer.apply("<split 5>")
            app._refresh_screen()
            await pilot.pause()
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
            await pilot.pause()
            # Use the scrolling API used by Textual's user scroll actions.
            pane.scroll_to(y=10, animate=False, immediate=True)
            await pilot.pause()
            before = visible_lower(app)
            app.buffer.write("new output\n" * 30 + "LATEST>")
            app._refresh_screen()
            await pilot.pause()
            assert pane.scroll_y == 10
            assert visible_lower(app) == before
            await pilot.resize_terminal(64, 24)
            await pilot.pause()
            assert pane.scroll_y == 10
            # Returning to the bottom via ordinary scrolling resumes following.
            pane.scroll_to(y=pane.max_scroll_y, animate=False, immediate=True)
            await pilot.pause()
            app.buffer.write("\nmore output\n" * 30 + "RESUMED>")
            app._refresh_screen()
            await pilot.pause()
            assert pane.scroll_y == pane.max_scroll_y
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
            await pilot.pause()
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
