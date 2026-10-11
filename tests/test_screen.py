import pytest

pytest.importorskip("textual")

from fernz._screen import ScreenBuffer


def lines(screen, window=0):
    return [line.rstrip() for line in screen.render(window).plain.splitlines()]


def test_screen_interprets_overwrites_and_literal_markup_in_order():
    screen = ScreenBuffer()
    screen.apply("<reset><size 20 5><split 2><top><at 1 1>old label")
    screen.apply("<at 1 1>new<at 1 4><clear-line><bottom><at 3 1><<bold>[x]")
    assert lines(screen, 1) == ["new", ""]
    assert lines(screen) == ["<bold>[x]", "", ""]
    screen.apply("<at 2 2 top>X")
    assert lines(screen, 1) == ["new", ""]  # Moving another cursor does not select it.
    assert lines(screen)[0] == "<bold>[x]X"
    screen.apply("<top>X")
    assert lines(screen, 1) == ["new", " X"]


def test_lower_window_wraps_words_and_scrolls_without_touching_upper():
    screen = ScreenBuffer(10, 4)
    screen.apply("<split 1><top>status<bottom><at 2 1>one two three four\nfive\nsix\nseven")
    assert lines(screen, 1) == ["status"]
    assert lines(screen) == ["one two", "three four", "five", "six", "seven"]
    screen.apply("<clear bottom><at 4 1>now")
    assert lines(screen) == ["one two", "three four", "", "", "now"]
    screen.apply("<reset><size 10 4><at 1 1><buffer off>one two three")
    assert lines(screen) == ["one two th", "ree", "", ""]


def test_upper_never_scrolls_and_styles_are_per_window():
    screen = ScreenBuffer(10, 4)
    screen.apply("<split 1><top><invert><bold>A\nB<bottom><at 2 1><italic>C")
    assert lines(screen, 1) == ["A"]
    top_style = screen.cells[1][0][0][1]
    bottom_style = screen.cells[0][1][0][1]
    assert top_style.reverse and top_style.bold and not top_style.italic
    assert bottom_style.italic and not bottom_style.reverse
    screen.apply("<color red #123456><normal><font 4><fixed>D")
    style = screen.cells[0][1][1][1]
    assert not style.italic
    assert style.color.get_truecolor() == (255, 0, 0)
    assert style.bgcolor.get_truecolor() == (18, 52, 86)
    screen.apply("<clear all>")
    assert lines(screen, 1) == [""]
    assert lines(screen) == ["", "", ""]
    assert screen.cells[0][1][0][1].bgcolor == style.bgcolor


def test_reset_discards_scrollback_and_resets_rendering_state():
    screen = ScreenBuffer(2, 2)
    screen.apply("a\nb\nc\nd\n<invert><buffer off>")
    assert screen.history
    screen.apply("<reset><size 3 3><bottom>x")
    assert not screen.history
    assert screen.split == 0 and screen.buffered
    assert lines(screen) == ["x", "", ""]
    assert not screen.cells[0][0][0][1].reverse
