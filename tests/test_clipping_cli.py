"""Clipping warnings at real VM input boundaries and finite screen rendering."""

import asyncio

import pytest

pytest.importorskip("textual")

from textual.widgets import Button, Input, Static

from fernz._rich_cli import ClippingWarning
from fernz._screen import ScreenBuffer

from .test_clipping import AREAD, CLIP, KEY, LOWER
from .test_rich_cli import player, settled


def test_offscreen_paint_does_not_overwrite_last_visible_row():
    screen = ScreenBuffer(3, 2)
    screen.apply("<split 2><top><at 2 1>ABC<at 3 1><invert>   \nXYZ")
    assert screen.render(1).plain.splitlines() == ["   ", "ABC"]
    assert screen.cursors[1] == (3, 3)
    assert len(screen.cells[1]) == 2


@pytest.mark.parametrize("dismissal", ["enter", "escape", "click"])
def test_warning_dismissal_preserves_pending_character_request(tmp_path, dismissal):
    app = player(tmp_path, CLIP + KEY + LOWER + AREAD, version=5, width=78, height=24)

    async def run():
        async with app.run_test(size=(80, 30)) as pilot:
            await settled(app, pilot)
            assert isinstance(app.screen, ClippingWarning)
            before = app.env.get_state()
            assert before.input_request.character
            assert "78 x 24" in str(app.screen.query_one("#clipping-message", Static).content)
            assert app.screen.query_one("#dismiss", Button).has_focus
            if dismissal == "click":
                await pilot.click("#dismiss")
            else:
                await pilot.press(dismissal)
            await pilot.pause()
            assert len(app.screen_stack) == 1
            assert app.env.get_state() == before
            assert app.character_input and app.query_one("#command", Input).disabled
            await pilot.press("x")
            await settled(app, pilot)
            assert not app.character_input
            assert app.query_one("#command", Input).has_focus
            assert len(app.screen_stack) == 1
            assert app.env.memory.read_word(app.env.story.header.globals_table + 2) == ord("x")

    asyncio.run(run())


def test_repeated_warnings_mute_and_restore_line_focus_without_advancing(tmp_path):
    code = (CLIP + LOWER + AREAD) * 4 + b"\xba"
    app = player(tmp_path, code, version=5, width=78, height=24)

    async def run():
        async with app.run_test(size=(80, 30)) as pilot:
            await settled(app, pilot)
            assert isinstance(app.screen, ClippingWarning)
            before = app.env.get_state()
            await pilot.press("enter")
            await pilot.pause()
            assert app.env.get_state() == before
            command = app.query_one("#command", Input)
            assert command.has_focus and not command.disabled
            command.value = "look"
            await pilot.press("enter")
            await settled(app, pilot)
            assert isinstance(app.screen, ClippingWarning)
            assert app.commands == ["look"]
            before = app.env.get_state()
            await pilot.click("#mute")
            await pilot.pause()
            assert app._mute_clipping_warnings
            assert app.env.get_state() == before
            assert command.has_focus
            command.value = "again"
            await pilot.press("enter")
            await settled(app, pilot)
            assert len(app.screen_stack) == 1 and command.has_focus
            assert app.env._machine.last_diagnostics  # UI mute does not mute VM reports.
            # Host restore and story restart keep the preference on the app.
            app.env.set_state(before)
            app._submit("restored")
            await settled(app, pilot)
            assert len(app.screen_stack) == 1
            app._advance(None)
            await settled(app, pilot)
            assert app._mute_clipping_warnings and len(app.screen_stack) == 1

    asyncio.run(run())
    fresh = player(tmp_path, code, version=5, width=78, height=24)
    assert not fresh._mute_clipping_warnings


@pytest.mark.parametrize("height", [25, 34])
def test_in_bounds_box_and_viewport_resize_do_not_warn(tmp_path, height):
    app = player(tmp_path, CLIP + LOWER + AREAD, version=5, width=78, height=height)

    async def run():
        async with app.run_test(size=(80, 30)) as pilot:
            await settled(app, pilot)
            assert len(app.screen_stack) == 1
            assert app.query_one("#command", Input).has_focus
            for size in [(68, 20), (123, 40)]:
                await pilot.resize_terminal(*size)
                await pilot.pause()
                assert len(app.screen_stack) == 1
                assert app._game_size == (78, height)

    asyncio.run(run())


def test_quit_during_warning_never_advances_story(tmp_path):
    app = player(tmp_path, CLIP + KEY + b"\xba", version=5, width=78, height=24)

    async def run():
        async with app.run_test(size=(80, 30)) as pilot:
            await settled(app, pilot)
            before = app.env.get_state()
            await pilot.press("ctrl+q")
        assert app.env.get_state() == before
        assert app.return_value == 0

    asyncio.run(run())


def test_save_dialog_finishes_before_warning_and_mute_survives_quetzal_restore(tmp_path):
    from fernz._rich_cli import FilePrompt

    from .test_rich_cli import dialog

    code = CLIP + bytes.fromhex("be 00 ff 10") + KEY + bytes.fromhex("be 01 ff 12 ba")
    app = player(tmp_path, code, version=5, width=78, height=24)
    path = tmp_path / "clipped.sav"

    async def run():
        async with app.run_test(size=(80, 30)) as pilot:
            await dialog(app, pilot)
            assert isinstance(app.screen, FilePrompt)
            app.screen.query_one(Input).value = str(path)
            await pilot.press("enter")
            await settled(app, pilot)
            assert path.is_file()
            assert isinstance(app.screen, ClippingWarning)
            # Keyboard focus navigation and activation of the second button.
            await pilot.press("tab", "enter")
            await pilot.pause()
            assert app._mute_clipping_warnings and app.character_input
            assert len(app.screen_stack) == 1
            await pilot.press("x")
            await dialog(app, pilot)
            assert isinstance(app.screen, FilePrompt)
            app.screen.query_one(Input).value = str(path)
            await pilot.press("enter")
            await settled(app, pilot)
            assert app._mute_clipping_warnings and app.character_input
            assert len(app.screen_stack) == 1
            assert app.env.get_state().output.cursors[1] == (25, 22)

    asyncio.run(run())


@pytest.mark.parametrize("size", [(68, 20), (123, 40)])
def test_warning_buttons_remain_visible_after_terminal_resize(tmp_path, size):
    app = player(tmp_path, CLIP + KEY, version=5, width=78, height=24)

    async def run():
        async with app.run_test(size=(80, 30)) as pilot:
            await settled(app, pilot)
            await pilot.resize_terminal(*size)
            await pilot.pause()
            for selector in ("#dismiss", "#mute"):
                button = app.screen.query_one(selector, Button)
                assert app.screen.region.contains_region(button.region)
            await pilot.click("#dismiss")
            await pilot.pause()
            assert app.character_input

    asyncio.run(run())
