"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .collectors import collect_files, collect_journal
from .config import ConfigError, CollectorConfig, TimeRange, load_config, resolve_time_range
from .os_detection import OSInfo, UnsupportedOSError, detect_ubuntu
from .output import CollectionResult, PackagingError, create_archive, write_manifest
from .safety import UnsafePathError, ensure_safe_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="incident-collector")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="collect logs and create a tar.gz archive")
    collect.add_argument("--config", type=Path, required=True)
    collect.add_argument("--start", help="ISO 8601 start timestamp; overrides YAML")
    collect.add_argument("--end", help="ISO 8601 end timestamp; overrides YAML")

    validate = subparsers.add_parser("validate-config", help="validate YAML without collecting")
    validate.add_argument("--config", type=Path, required=True)
    validate.add_argument("--start", help="ISO 8601 start timestamp; overrides YAML")
    validate.add_argument("--end", help="ISO 8601 end timestamp; overrides YAML")
    return parser


def _resolve_directory(path: Path) -> Path:
    return path if path.is_absolute() else Path.cwd() / path


def _validate(config_path: Path, start: str | None, end: str | None) -> tuple[CollectorConfig, TimeRange]:
    config = load_config(config_path)
    return config, resolve_time_range(config, start, end)


def _run_collection(config: CollectorConfig, time_range: TimeRange) -> int:
    started_at = datetime.now().astimezone()
    os_info: OSInfo = detect_ubuntu()
    output_directory = ensure_safe_directory(_resolve_directory(config.output_directory))
    temp_parent = (
        ensure_safe_directory(_resolve_directory(config.temporary_directory))
        if config.temporary_directory is not None
        else None
    )

    warnings: list[str] = []
    if time_range.end > datetime.now(time_range.end.tzinfo):
        warnings.append("requested time range includes a future timestamp")

    with tempfile.TemporaryDirectory(prefix="incident-collector-", dir=temp_parent) as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir()
        results: list[CollectionResult] = []

        if config.collect_journal:
            results.append(collect_journal(time_range, staging))
        else:
            results.append(CollectionResult("journal-system", "skipped", reason="disabled by configuration"))

        if config.continue_on_error or not any(item.status == "failed" for item in results):
            results.extend(collect_files(config.log_paths, staging))

        if config.include_manifest:
            write_manifest(
                staging / "manifest.json",
                started_at=started_at,
                time_range=time_range,
                target_alias=config.target_alias,
                os_info=os_info,
                collections=results,
                warnings=warnings,
            )

        archive, checksum = create_archive(
            staging,
            output_directory,
            config.target_alias,
            time_range,
            include_checksum=config.include_checksums,
        )

    print(f"archive: {archive}")
    if checksum is not None:
        print(f"checksum: {checksum}")
    return 1 if any(item.status in {"failed", "partial"} for item in results) else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config, time_range = _validate(args.config, args.start, args.end)
        if args.command == "validate-config":
            print("configuration is valid")
            return 0
        return _run_collection(config, time_range)
    except (ConfigError, UnsupportedOSError, UnsafePathError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except PackagingError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 6


if __name__ == "__main__":
    raise SystemExit(main())
