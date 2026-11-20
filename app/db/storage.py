"""Where evidence files are kept on disk, and what may be filed there.

The database stores a relative path; the bytes stay on the filesystem. A
relative path means the folder can be moved with the installation without
every attachment row having to be rewritten.

Nothing here decides who may file a record - that is the repository's
job. This module only answers "may this file become evidence, and where
does the copy go".
"""

from __future__ import annotations

import hashlib
import mimetypes
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.db.connection import DatabaseError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FOLDER = "evidence_files"

# The largest file the app will copy in one go, unless a deployment asks
# for less. A digital evidence item is usually a photograph, a document
# scan or a clip, not a disk image.
MAX_FILE_BYTES = 25 * 1024 * 1024

# What an evidence file plausibly is. Anything else is refused before it
# reaches the store: an executable in an evidence folder is a liability,
# not a file. A document can carry a macro, so the allowlist is about not
# running things from the store rather than about format authenticity.
ALLOWED_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff", ".bmp", ".heic",
    ".pdf", ".txt", ".csv", ".rtf", ".odt", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".mp4", ".avi", ".mov", ".mkv", ".webm", ".mp3", ".wav",
    ".m4a", ".amr", ".zip", ".rar", ".7z", ".tar", ".gz",
})

_READ_BLOCK = 1024 * 1024


@dataclass(frozen=True)
class StoredFile:
    """What was filed, ready to be inserted as an attachment row."""

    relative_path: str
    original_name: str
    mime_type: str | None
    size_bytes: int
    sha256: str


def evidence_root(folder: str | Path | None = None) -> Path:
    """The store, absolute. A relative setting is taken from the project."""
    root = Path(folder) if folder else PROJECT_ROOT / DEFAULT_FOLDER
    return root if root.is_absolute() else PROJECT_ROOT / root


def sha256_of(path: Path) -> str:
    """The hash of a file's bytes, read in blocks so a large clip fits."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_READ_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def human_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} bytes"


def validate(source: str | Path, *, allowed: frozenset[str] = ALLOWED_EXTENSIONS,
             max_bytes: int = MAX_FILE_BYTES) -> Path:
    """Check a file may be evidence at all, and hand back the path.

    Kept apart from :func:`store` so a caller can reject an upload before
    it spends a copy writing something that will not be filed.
    """
    path = Path(source)
    if not path.is_file():
        raise DatabaseError(f"There is no file to attach at '{path.name}'.")

    extension = path.suffix.lower()
    if extension not in allowed:
        raise DatabaseError(
            f"'{path.name}' is a {extension or 'file with no extension'}, which "
            "cannot be filed as evidence.")

    size_bytes = path.stat().st_size
    if size_bytes == 0:
        raise DatabaseError(f"'{path.name}' is empty, so there is nothing to file.")
    if size_bytes > max_bytes:
        raise DatabaseError(
            f"'{path.name}' is {human_size(size_bytes)}, over the "
            f"{human_size(max_bytes)} limit for one attachment.")
    return path


def store(source: str | Path, *, root: Path, evidence_id: int,
          allowed: frozenset[str] = ALLOWED_EXTENSIONS,
          max_bytes: int = MAX_FILE_BYTES) -> StoredFile:
    """Copy one file into the store and describe what was filed.

    The destination name is generated, never taken from the upload, so a
    second 'scene.jpg' cannot land on top of the first one. The copy is
    written beside the destination and renamed into place, which means a
    half-copied file is never recorded as filed.

    Raises :class:`DatabaseError` with a message fit to show the user
    when the file may not be evidence at all.
    """
    path = validate(source, allowed=allowed, max_bytes=max_bytes)
    size_bytes = path.stat().st_size

    folder = root / str(evidence_id)
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"{uuid.uuid4().hex}{path.suffix.lower()}"
    if destination.exists():
        raise DatabaseError(
            "A file is already filed under that name. Nothing was overwritten.")

    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        shutil.copyfile(path, temporary)
        if temporary.stat().st_size != size_bytes:
            raise DatabaseError(
                f"'{path.name}' changed while it was being copied. Nothing was filed.")
        digest = sha256_of(temporary)
        temporary.replace(destination)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise DatabaseError(f"The file could not be filed: {exc}") from exc
    except BaseException:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise

    return StoredFile(
        relative_path=destination.relative_to(root).as_posix(),
        original_name=path.name,
        mime_type=mimetypes.guess_type(path.name)[0],
        size_bytes=size_bytes,
        sha256=digest,
    )
