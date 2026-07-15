"""YAML configuration and time-range validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

class ConfigError(ValueError):
    """Raised when configuration cannot be used safely."""


@dataclass(frozen=True)
class TimeRange:
    start: datetime
    end: datetime
    timezone: str


@dataclass(frozen=True)
class CollectorConfig:
    target_os: str
    target_alias: str
    start_time: str
    end_time: str
    timezone: str
    output_directory: Path
    temporary_directory: Path | None
    continue_on_error: bool
    collect_journal: bool
    log_paths: tuple[str, ...]
    include_manifest: bool
    include_checksums: bool


def _mapping(value: Any, key: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"'{key}' must be a mapping")
    return value


def _boolean(value: Any, key: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ConfigError(f"'{key}' must be true or false")
    return value


def _safe_config_path(value: str, key: str) -> Path:
    path = Path(value)
    if ".." in path.parts:
        raise ConfigError(f"'{key}' must not contain path traversal")
    return path


def load_config(path: Path) -> CollectorConfig:
    if not path.exists() or not path.is_file():
        raise ConfigError(f"configuration file not found: {path}")
    if path.is_symlink():
        raise ConfigError("configuration file must not be a symbolic link")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"unable to read YAML configuration: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("configuration root must be a mapping")

    target = _mapping(raw.get("target"), "target")
    collection = _mapping(raw.get("collection"), "collection")
    system_logs = _mapping(raw.get("system_logs"), "system_logs")
    log_paths = _mapping(raw.get("log_paths"), "log_paths")
    output = _mapping(raw.get("output"), "output")

    includes = log_paths.get("include", [])
    if not isinstance(includes, list) or not all(isinstance(item, str) for item in includes):
        raise ConfigError("'log_paths.include' must be a list of paths")

    output_directory = str(collection.get("output_directory", "./output"))
    temporary_directory_raw = str(collection.get("temporary_directory", "")).strip()
    archive_format = output.get("archive_format", "tar.gz")
    if archive_format != "tar.gz":
        raise ConfigError("MVP supports only the tar.gz archive format")

    target_os = str(target.get("os", "auto"))
    if target_os not in {"auto", "ubuntu-24.04"}:
        raise ConfigError("target.os must be 'auto' or 'ubuntu-24.04'")

    target_alias = str(target.get("alias", "TARGET_001"))
    if not target_alias or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in target_alias):
        raise ConfigError("target.alias may contain only A-Z, 0-9, '_' and '-'")

    return CollectorConfig(
        target_os=target_os,
        target_alias=target_alias,
        start_time=str(collection.get("start_time", "")),
        end_time=str(collection.get("end_time", "")),
        timezone=str(collection.get("timezone", "UTC")),
        output_directory=_safe_config_path(output_directory, "collection.output_directory"),
        temporary_directory=(
            _safe_config_path(temporary_directory_raw, "collection.temporary_directory")
            if temporary_directory_raw
            else None
        ),
        continue_on_error=_boolean(collection.get("continue_on_error"), "collection.continue_on_error", True),
        collect_journal=(
            _boolean(system_logs.get("enabled"), "system_logs.enabled", True)
            and _boolean(system_logs.get("collect_journal"), "system_logs.collect_journal", True)
        ),
        log_paths=tuple(includes),
        include_manifest=_boolean(output.get("include_manifest"), "output.include_manifest", True),
        include_checksums=_boolean(output.get("include_checksums"), "output.include_checksums", True),
    )


def _parse_timestamp(value: str, timezone_name: str, field_name: str) -> datetime:
    if not value.strip():
        raise ConfigError(f"{field_name} is required")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ConfigError(f"{field_name} must be an ISO 8601 timestamp") from exc

    if parsed.tzinfo is None:
        try:
            timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ConfigError(f"unknown timezone: {timezone_name}") from exc
        parsed = parsed.replace(tzinfo=timezone)
    return parsed


def resolve_time_range(
    config: CollectorConfig,
    start_override: str | None = None,
    end_override: str | None = None,
) -> TimeRange:
    start = _parse_timestamp(start_override or config.start_time, config.timezone, "start_time")
    end = _parse_timestamp(end_override or config.end_time, config.timezone, "end_time")
    if start >= end:
        raise ConfigError("start_time must be earlier than end_time")
    return TimeRange(start=start, end=end, timezone=config.timezone)
