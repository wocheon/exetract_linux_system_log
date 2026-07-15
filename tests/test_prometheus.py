from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from incident_collector.collectors.prometheus import collect_prometheus
from incident_collector.config import PrometheusConfig, TimeRange


def _config(**overrides) -> PrometheusConfig:
    values = {
        "enabled": True,
        "base_url": "https://prometheus.example.internal:9090",
        "bearer_token_env": "",
        "verify_tls": True,
        "timeout_seconds": 30,
        "step_seconds": 60,
        "rate_interval": "5m",
        "instance": "target-01:9100",
        "max_points_per_query": 10000,
    }
    values.update(overrides)
    return PrometheusConfig(**values)


def _time_range(hours: int = 1) -> TimeRange:
    return TimeRange(
        datetime.fromisoformat("2026-07-15T10:00:00+09:00"),
        datetime.fromisoformat(f"2026-07-15T{10 + hours:02d}:00:00+09:00"),
        "Asia/Seoul",
    )


def _matrix_response() -> bytes:
    return json.dumps(
        {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"instance": "target-01:9100", "job": "node-exporter"},
                        "values": [[1752541200, "10.5"], [1752541260, "11.5"]],
                    }
                ],
            },
        }
    ).encode()


def test_collects_three_range_queries_as_json_and_csv(tmp_path: Path, monkeypatch) -> None:
    requests = []
    monkeypatch.setenv("PROM_TOKEN", "secret-token")

    def fake_transport(url, headers, timeout, verify_tls):
        requests.append((url, headers, timeout, verify_tls))
        return _matrix_response()

    result = collect_prometheus(
        _config(bearer_token_env="PROM_TOKEN"),
        _time_range(),
        tmp_path,
        transport=fake_transport,
    )

    assert result.status == "success"
    assert len(requests) == 3
    assert all(request[1]["Authorization"] == "Bearer secret-token" for request in requests)
    parameters = [parse_qs(urlparse(request[0]).query) for request in requests]
    assert all(item["start"] == ["2026-07-15T10:00:00+09:00"] for item in parameters)
    assert all(item["end"] == ["2026-07-15T11:00:00+09:00"] for item in parameters)
    queries = [item["query"][0] for item in parameters]
    assert all('instance="target-01:9100"' in query for query in queries)
    assert any("[5m]" in query for query in queries)

    document = json.loads((tmp_path / "metrics/prometheus/metrics.json").read_text(encoding="utf-8"))
    assert [record["status"] for record in document["queries"]] == ["success"] * 3
    with (tmp_path / "metrics/prometheus/metrics.csv").open(encoding="utf-8", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))
    assert len(rows) == 6
    assert {row["metric"] for row in rows} == {
        "cpu_usage_percent",
        "memory_usage_percent",
        "load_average_1m",
    }


def test_records_partial_results(tmp_path: Path) -> None:
    def fake_transport(url, headers, timeout, verify_tls):
        query = parse_qs(urlparse(url).query)["query"][0]
        if "node_cpu_seconds_total" in query:
            raise TimeoutError("request timed out")
        if "node_memory_MemAvailable_bytes" in query:
            return json.dumps(
                {"status": "success", "data": {"resultType": "matrix", "result": []}}
            ).encode()
        return _matrix_response()

    result = collect_prometheus(_config(), _time_range(), tmp_path, transport=fake_transport)

    assert result.status == "partial"
    document = json.loads((tmp_path / "metrics/prometheus/metrics.json").read_text(encoding="utf-8"))
    assert [record["status"] for record in document["queries"]] == ["failed", "skipped", "success"]


def test_rejects_excessive_point_count_without_network(tmp_path: Path) -> None:
    called = False

    def fake_transport(url, headers, timeout, verify_tls):
        nonlocal called
        called = True
        return _matrix_response()

    result = collect_prometheus(
        _config(step_seconds=1, max_points_per_query=10),
        _time_range(),
        tmp_path,
        transport=fake_transport,
    )

    assert result.status == "failed"
    assert "increase step_seconds" in (result.reason or "")
    assert called is False


def test_disabled_prometheus_is_skipped(tmp_path: Path) -> None:
    result = collect_prometheus(_config(enabled=False), _time_range(), tmp_path)

    assert result.status == "skipped"
    assert not (tmp_path / "metrics").exists()
