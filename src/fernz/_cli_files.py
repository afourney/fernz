"""Filesystem operations shared by the two CLI frontends."""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def write_save(path: Path, data: bytes) -> None:
    """Publish a complete save atomically after the frontend obtains consent."""
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as file:
            temporary = Path(file.name)
            file.write(data)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
