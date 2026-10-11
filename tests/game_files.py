"""Download the test corpus without adding dependencies to the Fernz library."""

from pathlib import Path, PurePosixPath
from shutil import copyfileobj
from stat import S_ISLNK
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile

GAMES_ARCHIVE_URL = "https://github.com/BYU-PCCL/z-machine-games/archive/master.zip"
SUITE_NAME = "jericho-game-suite"
ARCHIVE_PREFIX = f"z-machine-games-master/{SUITE_NAME}/"


def ensure_jericho_games(games_dir: Path) -> Path:
    """Return the suite directory, downloading only when games_dir is absent.

    Existing directories are left untouched. New data is staged on the same
    filesystem so an interrupted download or extraction cannot leave a partial
    games directory that would suppress subsequent downloads.
    """
    suite_dir = games_dir / SUITE_NAME
    if games_dir.exists():
        if not suite_dir.is_dir():
            raise RuntimeError(
                f"{games_dir} already exists but {suite_dir} is missing. "
                "Populate the suite manually or move the existing games path "
                "aside to allow a download."
            )
        return suite_dir

    try:
        with TemporaryDirectory(prefix=".fernz-games-", dir=games_dir.parent) as tmp:
            staging = Path(tmp)
            archive_path = staging / "games.zip"
            with (
                urlopen(GAMES_ARCHIVE_URL, timeout=60) as response,
                archive_path.open("wb") as archive_file,
            ):
                copyfileobj(response, archive_file)

            staged_games = staging / "games"
            staged_suite = staged_games / SUITE_NAME
            staged_suite.mkdir(parents=True)
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
                        or S_ISLNK(entry.external_attr >> 16)
                    ):
                        raise ValueError(f"Unsafe game archive entry: {entry.filename}")
                    with (
                        archive.open(entry) as source,
                        (staged_suite / name).open("xb") as target,
                    ):
                        copyfileobj(source, target)

            if not (staged_suite / "zork1.z5").is_file():
                raise ValueError("The archive does not contain the expected Zork I file")
            staged_games.rename(games_dir)
    except (OSError, BadZipFile, ValueError) as exc:
        raise RuntimeError(
            f"Could not prepare {suite_dir} from {GAMES_ARCHIVE_URL}: {exc}"
        ) from exc

    return suite_dir
