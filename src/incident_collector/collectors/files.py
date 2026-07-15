"""Streaming collector for explicitly configured log files."""

from __future__ import annotations

import shutil
from pathlib import Path

from ..output import CollectionResult
from ..safety import (
    UnsafePathError,
    archive_relative_path,
    open_source_binary,
    validate_source_file,
)


def collect_files(raw_paths: tuple[str, ...], staging_directory: Path) -> list[CollectionResult]:
    results: list[CollectionResult] = []
    destination_root = staging_directory / "logs/var-log"

    for raw_path in raw_paths:
        collection_name = f"file:{raw_path}"
        destination: Path | None = None
        try:
            source = validate_source_file(raw_path)
        except FileNotFoundError:
            results.append(CollectionResult(collection_name, "skipped", reason="file not found"))
            continue
        except (OSError, UnsafePathError) as exc:
            results.append(CollectionResult(collection_name, "failed", reason=str(exc)))
            continue

        try:
            relative_source = archive_relative_path(source)
            relative_output = Path("logs/var-log") / relative_source
            destination = staging_directory / relative_output
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.absolute().is_relative_to(destination_root.absolute()):
                raise UnsafePathError("destination escaped the log output directory")
            with open_source_binary(source) as source_file, destination.open("xb") as output_file:
                shutil.copyfileobj(source_file, output_file, length=1024 * 1024)
        except (OSError, UnsafePathError) as exc:
            if destination is not None:
                destination.unlink(missing_ok=True)
            results.append(CollectionResult(collection_name, "failed", reason=str(exc)))
            continue

        results.append(
            CollectionResult(
                collection_name,
                "success",
                output=relative_output.as_posix(),
            )
        )

    return results
