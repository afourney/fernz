"""Download the game suite using only the standard library."""

from http.client import HTTPException
from pathlib import Path, PurePosixPath, PureWindowsPath
from shutil import copyfileobj
from stat import S_ISLNK
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

GAMES_ARCHIVE_URL = "https://github.com/BYU-PCCL/z-machine-games/archive/master.zip"
SUITE_NAME = "jericho-game-suite"
ARCHIVE_PREFIX = f"z-machine-games-master/{SUITE_NAME}/"


def ensure_jericho_games(games_dir: Path) -> Path:
    """Return games_dir, downloading the suite directly into it when absent.

    Existing directories are left untouched. New data is staged on the same
    filesystem so an interrupted download or extraction cannot leave a partial
    games directory that would suppress subsequent downloads.
    """
    if games_dir.exists() or games_dir.is_symlink():
        if not (games_dir / "zork1.z5").is_file():
            raise RuntimeError(
                f"{games_dir} already exists but {games_dir / 'zork1.z5'} is missing. "
                "Populate the suite manually or move the existing games path "
                "aside to allow a download."
            )
        return games_dir

    try:
        games_dir.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".fernz-games-", dir=games_dir.parent) as tmp:
            staging = Path(tmp)
            archive_path = staging / "games.zip"
            with (
                urlopen(GAMES_ARCHIVE_URL, timeout=60) as response,
                archive_path.open("wb") as archive_file,
            ):
                copyfileobj(response, archive_file)

            staged_games = staging / "games"
            staged_games.mkdir()
            with ZipFile(archive_path) as archive:
                for entry in archive.infolist():
                    if not entry.filename.startswith(ARCHIVE_PREFIX) or entry.is_dir():
                        continue
                    name = entry.filename.removeprefix(ARCHIVE_PREFIX)
                    path = PurePosixPath(name)
                    if (
                        len(path.parts) != 1
                        or path.name != name
                        or name in {".", ".."}
                        or "\\" in name
                        or ":" in name
                        or name.endswith((".", " "))
                        or PureWindowsPath(name).is_reserved()
                        or S_ISLNK(entry.external_attr >> 16)
                    ):
                        raise ValueError(f"Unsafe game archive entry: {entry.filename}")
                    with (
                        archive.open(entry) as source,
                        (staged_games / name).open("xb") as target,
                    ):
                        copyfileobj(source, target)

            if not (staged_games / "zork1.z5").is_file():
                raise ValueError("The archive does not contain the expected Zork I file")
            staged_games.rename(games_dir)
    except (
        OSError,
        HTTPException,
        BadZipFile,
        EOFError,
        ZlibError,
        ValueError,
        RuntimeError,
    ) as exc:
        raise RuntimeError(
            f"Could not prepare {games_dir} from {GAMES_ARCHIVE_URL}: {exc}"
        ) from exc

    return games_dir
