from __future__ import annotations

from pathlib import Path

import pytest

from incident_collector.config import ConfigError, load_config, resolve_time_range


def _write_config(path: Path, start: str, end: str, output: str = "./output") -> None:
    path.write_text(
        f"""
target:
  os: auto
  alias: TARGET_001
collection:
  start_time: '{start}'
  end_time: '{end}'
  timezone: Asia/Seoul
  output_directory: '{output}'
system_logs:
  enabled: true
  collect_journal: true
log_paths:
  include: []
output:
  archive_format: tar.gz
""",
        encoding="utf-8",
    )


def test_load_config_and_validate_time_range(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, "2026-07-15T10:00:00+09:00", "2026-07-15T11:00:00+09:00")

    time_range = resolve_time_range(load_config(config_path))

    assert time_range.start.hour == 10
    assert time_range.end.hour == 11
    assert time_range.timezone == "Asia/Seoul"


def test_rejects_reversed_time_range(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, "2026-07-15T11:00:00+09:00", "2026-07-15T10:00:00+09:00")

    with pytest.raises(ConfigError, match="earlier"):
        resolve_time_range(load_config(config_path))


def test_rejects_output_path_traversal(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, "2026-07-15T10:00:00+09:00", "2026-07-15T11:00:00+09:00", "../output")

    with pytest.raises(ConfigError, match="path traversal"):
        load_config(config_path)


def test_loads_enabled_prometheus_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, "2026-07-15T10:00:00+09:00", "2026-07-15T11:00:00+09:00")
    with config_path.open("a", encoding="utf-8") as config_file:
        config_file.write(
            """
prometheus:
  enabled: true
  base_url: 'https://prometheus.example.internal:9090'
  bearer_token_env: 'PROMETHEUS_BEARER_TOKEN'
  verify_tls: true
  timeout_seconds: 20
  step_seconds: 30
  rate_interval: '5m'
  instance: 'target-01:9100'
  max_points_per_query: 5000
"""
        )

    config = load_config(config_path)

    assert config.prometheus.enabled is True
    assert config.prometheus.instance == "target-01:9100"
    assert config.prometheus.step_seconds == 30


def test_rejects_invalid_prometheus_url(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, "2026-07-15T10:00:00+09:00", "2026-07-15T11:00:00+09:00")
    with config_path.open("a", encoding="utf-8") as config_file:
        config_file.write(
            """
prometheus:
  enabled: true
  base_url: 'prometheus.example.internal:9090'
  instance: 'target-01:9100'
"""
        )

    with pytest.raises(ConfigError, match="absolute HTTP"):
        load_config(config_path)
