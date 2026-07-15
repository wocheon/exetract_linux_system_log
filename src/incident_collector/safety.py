"""Filesystem safety checks used by collectors and packaging."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import BinaryIO


class UnsafePathError(ValueError):
    """Raised when a path can escape or redirect collection."""


def _reject_traversal(path: Path) -> None:
    if ".." in path.parts:
        raise UnsafePathError("path traversal is not allowed")


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.exists() or current.is_symlink():
            if current.is_symlink():
                raise UnsafePathError(f"symbolic links are not allowed: {current}")


def validate_source_file(raw_path: str) -> Path:
    path = Path(raw_path)
    _reject_traversal(path)
    if not path.is_absolute():
        raise UnsafePathError("log source path must be absolute")
    _reject_symlink_components(path)
    if not path.exists():
        raise FileNotFoundError(path)
    if not path.is_file():
        raise UnsafePathError("log source must be a regular file")
    if not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode):
        raise UnsafePathError("log source must be a regular file")
    return path


def open_source_binary(path: Path) -> BinaryIO:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise UnsafePathError("log source changed or is not a regular file")
        return os.fdopen(descriptor, "rb")
    except Exception:
        os.close(descriptor)
        raise


def archive_relative_path(source: Path) -> Path:
    relative_parts = [part.replace(":", "") for part in source.parts[1:]]
    if not relative_parts or any(part in {"", ".", ".."} for part in relative_parts):
        raise UnsafePathError("unable to derive a safe archive path")
    return Path(*relative_parts)


def ensure_safe_directory(path: Path) -> Path:
    _reject_traversal(path)
    absolute = path.absolute()
    _reject_symlink_components(absolute)
    absolute.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(absolute)
    if not absolute.is_dir():
        raise UnsafePathError(f"not a directory: {absolute}")
    return absolute
