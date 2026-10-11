from io import BytesIO
from urllib.error import URLError
from zipfile import ZipFile

import pytest

from fernz import _games as game_files


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_existing_suite_is_unchanged_and_needs_no_network(tmp_path, monkeypatch):
    games = tmp_path / "games"
    games.mkdir()
    (games / "zork1.z5").write_bytes(b"local data")

    def no_download(*args, **kwargs):
        pytest.fail("An existing games directory must not trigger a download")

    monkeypatch.setattr(game_files, "urlopen", no_download)
    assert game_files.ensure_jericho_games(games) == games
    assert [(p.name, p.read_bytes()) for p in games.iterdir()] == [("zork1.z5", b"local data")]


def test_existing_games_without_suite_is_left_untouched(tmp_path, monkeypatch):
    games = tmp_path / "games"
    games.mkdir()
    (games / "notes.txt").write_text("keep me")

    def no_download(*args, **kwargs):
        pytest.fail("An existing games directory must not trigger a download")

    monkeypatch.setattr(game_files, "urlopen", no_download)
    with pytest.raises(RuntimeError, match="already exists"):
        game_files.ensure_jericho_games(games)
    assert [(p.name, p.read_text()) for p in games.iterdir()] == [("notes.txt", "keep me")]


def test_download_keeps_the_complete_requested_suite(tmp_path, monkeypatch):
    archive = zip_bytes(
        {
            "z-machine-games-master/README.md": b"upstream readme",
            "z-machine-games-master/jericho-game-suite/zork1.z5": b"\x03zork",
            "z-machine-games-master/jericho-game-suite/trinity.z4": b"\x04trinity",
            "z-machine-games-master/jericho-game-suite/lgop.z3": b"\x03lgop",
            "z-machine-games-master/autoplay-game-suite/Advent.z5": b"other suite",
            "z-machine-games-master/the-large-game-collection.zip": b"other archive",
        }
    )
    requests = []

    def download(url, *, timeout):
        requests.append(url)
        return BytesIO(archive)

    monkeypatch.setattr(game_files, "urlopen", download)
    games = tmp_path / "games"
    suite = game_files.ensure_jericho_games(games)
    assert suite == games
    assert {
        p.relative_to(games).as_posix(): p.read_bytes() for p in games.rglob("*") if p.is_file()
    } == {
        "zork1.z5": b"\x03zork",
        "trinity.z4": b"\x04trinity",
        "lgop.z3": b"\x03lgop",
    }
    assert game_files.ensure_jericho_games(games) == suite
    assert requests == [game_files.GAMES_ARCHIVE_URL]
    assert list(tmp_path.iterdir()) == [games]


def test_failed_download_can_be_retried(tmp_path, monkeypatch):
    def fail_download(*args, **kwargs):
        raise URLError("connection lost")

    monkeypatch.setattr(game_files, "urlopen", fail_download)
    games = tmp_path / "games"
    with pytest.raises(RuntimeError, match="connection lost"):
        game_files.ensure_jericho_games(games)
    assert list(tmp_path.iterdir()) == []

    archive = zip_bytes({game_files.ARCHIVE_PREFIX + "zork1.z5": b"\x03zork"})
    monkeypatch.setattr(game_files, "urlopen", lambda *a, **kw: BytesIO(archive))
    assert (game_files.ensure_jericho_games(games) / "zork1.z5").is_file()


@pytest.mark.parametrize("archive", [b"not a ZIP file", zip_bytes({"README": b"empty"})])
def test_invalid_archive_does_not_create_games(tmp_path, monkeypatch, archive):
    monkeypatch.setattr(game_files, "urlopen", lambda *a, **kw: BytesIO(archive))
    with pytest.raises(RuntimeError, match="Could not prepare"):
        game_files.ensure_jericho_games(tmp_path / "games")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("name", ["../escaped.z3", "/escaped.z3", "..\\escaped.z3"])
def test_unsafe_archive_does_not_write_outside_staging(tmp_path, monkeypatch, name):
    archive = zip_bytes(
        {
            game_files.ARCHIVE_PREFIX + "zork1.z5": b"\x03zork",
            game_files.ARCHIVE_PREFIX + name: b"unsafe",
        }
    )
    monkeypatch.setattr(game_files, "urlopen", lambda *a, **kw: BytesIO(archive))
    with pytest.raises(RuntimeError, match="Unsafe game archive entry"):
        game_files.ensure_jericho_games(tmp_path / "games")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "name", ["C:escape.z3", "nested/story.z3", "CON", "story.z3.", "story.z3 "]
)
def test_nonportable_archive_names_are_rejected(tmp_path, monkeypatch, name):
    archive = zip_bytes({game_files.ARCHIVE_PREFIX + name: b"unsafe"})
    monkeypatch.setattr(game_files, "urlopen", lambda *a, **kw: BytesIO(archive))
    with pytest.raises(RuntimeError, match="Unsafe game archive entry"):
        game_files.ensure_jericho_games(tmp_path / "games")
    assert not list(tmp_path.iterdir())


def test_archive_symlink_is_rejected(tmp_path, monkeypatch):
    from stat import S_IFLNK
    from zipfile import ZipInfo

    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        link = ZipInfo(game_files.ARCHIVE_PREFIX + "zork1.z5")
        link.create_system = 3
        link.external_attr = (S_IFLNK | 0o777) << 16
        archive.writestr(link, "../../outside")
    monkeypatch.setattr(game_files, "urlopen", lambda *a, **kw: BytesIO(buffer.getvalue()))
    with pytest.raises(RuntimeError, match="Unsafe game archive entry"):
        game_files.ensure_jericho_games(tmp_path / "games")
    assert not list(tmp_path.iterdir())


def test_extraction_failure_cleans_up_and_preserves_files(tmp_path, monkeypatch):
    archive = zip_bytes({game_files.ARCHIVE_PREFIX + "zork1.z5": b"game"})
    monkeypatch.setattr(game_files, "urlopen", lambda *a, **kw: BytesIO(archive))
    original = game_files.copyfileobj
    calls = 0

    def fail_extract(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("disk full")
        original(source, target)

    monkeypatch.setattr(game_files, "copyfileobj", fail_extract)
    keep = tmp_path / "notes.txt"
    keep.write_bytes(b"keep")
    with pytest.raises(RuntimeError, match="disk full"):
        game_files.ensure_jericho_games(tmp_path / "games")
    assert list(tmp_path.iterdir()) == [keep]
    assert keep.read_bytes() == b"keep"


def test_truncated_download_is_reported_and_cleaned_up(tmp_path, monkeypatch):
    from http.client import IncompleteRead

    def fail_copy(*args):
        raise IncompleteRead(b"partial", 100)

    monkeypatch.setattr(game_files, "urlopen", lambda *a, **kw: BytesIO(b"partial"))
    monkeypatch.setattr(game_files, "copyfileobj", fail_copy)
    with pytest.raises(RuntimeError, match="IncompleteRead"):
        game_files.ensure_jericho_games(tmp_path / "games")
    assert not list(tmp_path.iterdir())


def test_destination_parent_is_a_file(tmp_path):
    parent = tmp_path / "file"
    parent.write_bytes(b"keep")
    with pytest.raises(RuntimeError, match="Could not prepare"):
        game_files.ensure_jericho_games(parent / "games")
    assert parent.read_bytes() == b"keep"


@pytest.mark.parametrize("kind", ["deflate", "eof"])
def test_decompression_errors_are_reported(tmp_path, monkeypatch, kind):
    from zlib import error as ZlibError

    archive = zip_bytes({game_files.ARCHIVE_PREFIX + "zork1.z5": b"game"})
    monkeypatch.setattr(game_files, "urlopen", lambda *a, **kw: BytesIO(archive))

    def fail_open(*args, **kwargs):
        raise ZlibError("invalid compressed data") if kind == "deflate" else EOFError("truncated")

    monkeypatch.setattr(game_files.ZipFile, "open", fail_open)
    with pytest.raises(RuntimeError, match="Could not prepare"):
        game_files.ensure_jericho_games(tmp_path / "games")
    assert not list(tmp_path.iterdir())
