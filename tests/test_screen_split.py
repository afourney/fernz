import pytest

pytest.importorskip("textual")

from fernz._screen import ScreenBuffer


def physical(screen):
    return screen.render(1).plain.splitlines() + screen.render(0).plain.splitlines()


def test_split_preserves_existing_physical_cells_and_styles():
    screen = ScreenBuffer(10, 5)
    screen.apply("<at 2 1><italic>abcdefghij<normal><split 3><top><at 2 4><invert>BOX")
    assert screen.render(1).plain.splitlines()[1] == "abcBOXghij"
    before = physical(screen)
    screen.apply("<split 1>")
    assert physical(screen) == before
    assert screen.cells[0][1][3][1].reverse
    assert screen.cells[0][1][0][1].italic
    screen.apply("<bottom><at 2 4><normal>new<split 3>")
    assert screen.render(1).plain.splitlines()[1] == "abcnewghij"


def test_collapsed_quote_scrolls_once_into_lower_history():
    screen = ScreenBuffer(10, 5)
    screen.apply("<split 3><top>status<at 3 1><invert>clue<normal><bottom><at 5 1><split 1>")
    screen.apply("\n\n\n\n\n")
    assert screen.render(0).plain.count("clue") == 1
    assert any("clue" in "".join(char for char, _ in row) for row in screen.history)
    assert screen.render(1).plain.strip() == "status"


@pytest.mark.parametrize("clear", ["top", "bottom", "all"])
def test_explicit_clear_does_not_resurrect_cells_after_resplit(clear):
    screen = ScreenBuffer(10, 5)
    screen.apply("<split 3><top><at 2 1>clue")
    if clear == "top":
        screen.apply("<clear top><split 0><split 3>")
    else:
        screen.apply(f"<split 0><clear {clear}><split 3>")
    assert "clue" not in screen.render(1).plain


def test_sherlock_shaped_quote_remains_after_same_response_shrinks_split():
    screen = ScreenBuffer(80, 24)
    screen.apply("<split 1><bottom><at 24 1>")
    screen.apply(
        "\n<split 8><top><at 1 1><invert><at 8 21>                                      "
        "<split 9><at 9 21> Visiting Hours: 7:00 a.m - 6:00 p.m. "
        "<split 10><at 10 21>                                      "
        "<normal><bottom><split 1><at 1 1 top><top><at 1 1><invert>status"
        "<normal><bottom>\n>"
    )
    assert screen.split == 1
    assert "Visiting Hours: 7:00 a.m - 6:00 p.m." in screen.render(0).plain
    assert screen.render(1).plain.strip() == "status"
