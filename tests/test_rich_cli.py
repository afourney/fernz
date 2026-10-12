import asyncio

import pytest

pytest.importorskip("textual")

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
                tail_row = next(
                    row for row in range(text.size.height) if "TAIL" in text.render_line(row).text
                )
                assert any(segment.style.bold for segment in text.render_line(tail_row))
                assert app.buffer.render(0).plain == logical
                assert app.env.get_state() == state
                if split:
                    upper = app.query_one("#upper-text")
                    assert upper.size.height == 1
                    assert upper.render_line(0).text == "UPPER" + " " * (logical_width - 9) + "HEAD"

    asyncio.run(run())
