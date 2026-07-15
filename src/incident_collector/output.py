"""Collection results, manifest writing, archive creation, and checksums."""

from __future__ import annotations

import hashlib
import json
import tarfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import __version__
from .config import TimeRange
from .os_detection import OSInfo
from .safety import UnsafePathError, ensure_safe_directory


COLLECTION_STATUSES = {"success", "partial", "failed", "skipped"}


@dataclass(frozen=True)
class CollectionResult:
    name: str
    status: str
    output: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in COLLECTION_STATUSES:
            raise ValueError(f"unsupported collection status: {self.status}")

    def as_dict(self) -> dict[str, str]:
        result = {"name": self.name, "status": self.status}
        if self.output is not None:
            result["output"] = self.output
        if self.reason is not None:
            result["reason"] = self.reason
        return result


class PackagingError(RuntimeError):
    """Raised when an archive cannot be produced safely."""


def write_manifest(
    destination: Path,
    *,
    started_at: datetime,
    time_range: TimeRange,
    target_alias: str,
    os_info: OSInfo,
    collections: list[CollectionResult],
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> None:
    payload = {
        "schema_version": "1.0",
        "collector_version": __version__,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now().astimezone().isoformat(),
        "requested_time_range": {
            "start": time_range.start.isoformat(),
            "end": time_range.end.isoformat(),
            "timezone": time_range.timezone,
        },
        "target": {"alias": target_alias, "os": os_info.pretty_name},
        "masking": {"enabled": False, "completed": False},
        "collections": [result.as_dict() for result in collections],
        "warnings": warnings or [],
        "errors": errors or [],
    }
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ensure_no_symlinks(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise PackagingError(f"symbolic link found in staging directory: {path}")


def create_archive(
    staging_directory: Path,
    output_directory: Path,
    target_alias: str,
    time_range: TimeRange,
    *,
    include_checksum: bool = True,
) -> tuple[Path, Path | None]:
    try:
        safe_output = ensure_safe_directory(output_directory)
        _ensure_no_symlinks(staging_directory)
    except (OSError, UnsafePathError) as exc:
        raise PackagingError(str(exc)) from exc

    base_name = (
        f"incident-collection-{target_alias}-"
        f"{time_range.start:%Y%m%dT%H%M%S}-{time_range.end:%Y%m%dT%H%M%S}"
    )
    archive = safe_output / f"{base_name}.tar.gz"
    if archive.exists() or archive.is_symlink():
        raise PackagingError(f"refusing to overwrite existing archive: {archive}")

    try:
        with tarfile.open(archive, mode="x:gz", dereference=False) as tar:
            tar.add(staging_directory, arcname=base_name, recursive=True)
    except (OSError, tarfile.TarError) as exc:
        archive.unlink(missing_ok=True)
        raise PackagingError(f"unable to create archive: {exc}") from exc

    if not include_checksum:
        return archive, None

    checksum_path = archive.with_suffix(archive.suffix + ".sha256")
    digest = hashlib.sha256()
    try:
        with archive.open("rb") as archive_file:
            for chunk in iter(lambda: archive_file.read(1024 * 1024), b""):
                digest.update(chunk)
        checksum_path.write_text(f"{digest.hexdigest()}  {archive.name}\n", encoding="ascii")
    except OSError as exc:
        archive.unlink(missing_ok=True)
        checksum_path.unlink(missing_ok=True)
        raise PackagingError(f"unable to create checksum: {exc}") from exc

    return archive, checksum_path

