"""YAML configuration and time-range validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse
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
class PrometheusConfig:
    enabled: bool
    base_url: str
    bearer_token_env: str
    verify_tls: bool
    timeout_seconds: int
    step_seconds: int
    rate_interval: str
    instance: str
    max_points_per_query: int


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
    prometheus: PrometheusConfig
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


def _positive_integer(value: Any, key: str, default: int, maximum: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > maximum:
        raise ConfigError(f"'{key}' must be an integer between 1 and {maximum}")
    return value


def _load_prometheus(raw: Any) -> PrometheusConfig:
    values = _mapping(raw, "prometheus")
    enabled = _boolean(values.get("enabled"), "prometheus.enabled", False)
    base_url = str(values.get("base_url", "")).strip().rstrip("/")
    token_env = str(values.get("bearer_token_env", "")).strip()
    instance = str(values.get("instance", "")).strip()
    rate_interval = str(values.get("rate_interval", "5m")).strip()

    if enabled:
        parsed_url = urlparse(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ConfigError("'prometheus.base_url' must be an absolute HTTP(S) URL")
        if parsed_url.username or parsed_url.password or parsed_url.query or parsed_url.fragment:
            raise ConfigError("'prometheus.base_url' must not contain credentials, query, or fragment")
        if not instance or "\n" in instance or "\r" in instance:
            raise ConfigError("'prometheus.instance' is required and must be one line")
        if token_env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token_env):
            raise ConfigError("'prometheus.bearer_token_env' must be a valid environment variable name")
        if not re.fullmatch(r"[1-9][0-9]*(?:ms|s|m|h|d|w|y)", rate_interval):
            raise ConfigError("'prometheus.rate_interval' must be a simple duration such as '5m'")

    return PrometheusConfig(
        enabled=enabled,
        base_url=base_url,
        bearer_token_env=token_env,
        verify_tls=_boolean(values.get("verify_tls"), "prometheus.verify_tls", True),
        timeout_seconds=_positive_integer(
            values.get("timeout_seconds"), "prometheus.timeout_seconds", 30, 300
        ),
        step_seconds=_positive_integer(values.get("step_seconds"), "prometheus.step_seconds", 60, 86400),
        rate_interval=rate_interval,
        instance=instance,
        max_points_per_query=_positive_integer(
            values.get("max_points_per_query"), "prometheus.max_points_per_query", 10000, 100000
        ),
    )


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
    prometheus = _load_prometheus(raw.get("prometheus"))
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
        prometheus=prometheus,
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
