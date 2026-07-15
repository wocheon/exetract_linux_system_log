"""Historical node_exporter metrics through the Prometheus range API."""

from __future__ import annotations

import csv
import json
import os
import ssl
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from ..config import PrometheusConfig, TimeRange
from ..output import CollectionResult


MAX_RESPONSE_BYTES = 25 * 1024 * 1024
Transport = Callable[[str, dict[str, str], int, bool], bytes]


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _http_get(url: str, headers: dict[str, str], timeout: int, verify_tls: bool) -> bytes:
    context = ssl.create_default_context()
    if not verify_tls:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    request = Request(url, headers=headers, method="GET")
    opener = build_opener(_NoRedirectHandler(), HTTPSHandler(context=context))
    with opener.open(request, timeout=timeout) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_RESPONSE_BYTES:
            raise ValueError("Prometheus response exceeds 25 MiB")
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("Prometheus response exceeds 25 MiB")
    return body


def _promql_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_queries(config: PrometheusConfig) -> dict[str, str]:
    instance = _promql_string(config.instance)
    selector = f'instance="{instance}"'
    return {
        "cpu_usage_percent": (
            "100 - (avg by (instance) "
            f"(rate(node_cpu_seconds_total{{{selector},mode=\"idle\"}}[{config.rate_interval}])) * 100)"
        ),
        "memory_usage_percent": (
            f"(1 - (node_memory_MemAvailable_bytes{{{selector}}} / "
            f"node_memory_MemTotal_bytes{{{selector}}})) * 100"
        ),
        "load_average_1m": f"node_load1{{{selector}}}",
    }


def _query_url(config: PrometheusConfig, time_range: TimeRange, query: str) -> str:
    parameters = urlencode(
        {
            "query": query,
            "start": time_range.start.isoformat(),
            "end": time_range.end.isoformat(),
            "step": str(config.step_seconds),
        }
    )
    return f"{config.base_url}/api/v1/query_range?{parameters}"


def _run_query(
    config: PrometheusConfig,
    time_range: TimeRange,
    query: str,
    headers: dict[str, str],
    transport: Transport,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        body = transport(
            _query_url(config, time_range, query),
            headers,
            config.timeout_seconds,
            config.verify_tls,
        )
        payload = json.loads(body.decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        return None, str(exc)[:500]

    if not isinstance(payload, dict) or payload.get("status") != "success":
        reason = payload.get("error") if isinstance(payload, dict) else "invalid JSON response"
        return None, str(reason or "Prometheus returned a non-success response")[:500]
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("result"), list):
        return None, "Prometheus response does not contain a matrix result"
    return payload, None


def _csv_rows(metric_name: str, payload: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for series in payload["data"]["result"]:
        if not isinstance(series, dict) or not isinstance(series.get("values"), list):
            continue
        labels = series.get("metric") if isinstance(series.get("metric"), dict) else {}
        labels_json = json.dumps(labels, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for sample in series["values"]:
            if isinstance(sample, list) and len(sample) == 2:
                rows.append(
                    {
                        "metric": metric_name,
                        "timestamp": str(sample[0]),
                        "value": str(sample[1]),
                        "labels": labels_json,
                    }
                )
    return rows


def _format_response_timestamps(payload: dict[str, Any], time_range: TimeRange) -> None:
    for series in payload["data"]["result"]:
        if not isinstance(series, dict) or not isinstance(series.get("values"), list):
            continue
        for sample in series["values"]:
            if not isinstance(sample, list) or len(sample) != 2:
                continue
            try:
                sample[0] = datetime.fromtimestamp(float(sample[0]), tz=time_range.start.tzinfo).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            except (TypeError, ValueError, OSError, OverflowError):
                continue


def collect_prometheus(
    config: PrometheusConfig,
    time_range: TimeRange,
    staging_directory: Path,
    transport: Transport = _http_get,
) -> CollectionResult:
    if not config.enabled:
        return CollectionResult("prometheus-node-exporter", "skipped", reason="disabled by configuration")

    point_count = int((time_range.end - time_range.start).total_seconds() // config.step_seconds) + 1
    if point_count > config.max_points_per_query:
        return CollectionResult(
            "prometheus-node-exporter",
            "failed",
            reason=(
                f"requested {point_count} points per query; increase step_seconds "
                f"or max_points_per_query ({config.max_points_per_query})"
            ),
        )

    headers = {"Accept": "application/json"}
    if config.bearer_token_env:
        token = os.environ.get(config.bearer_token_env)
        if not token:
            return CollectionResult(
                "prometheus-node-exporter",
                "failed",
                reason=f"environment variable is not set: {config.bearer_token_env}",
            )
        headers["Authorization"] = f"Bearer {token}"

    query_records: list[dict[str, Any]] = []
    csv_rows: list[dict[str, str]] = []
    for name, query in build_queries(config).items():
        payload, error = _run_query(config, time_range, query, headers, transport)
        if error is not None:
            query_records.append({"name": name, "query": query, "status": "failed", "reason": error})
            continue
        assert payload is not None
        _format_response_timestamps(payload, time_range)
        rows = _csv_rows(name, payload)
        if not rows:
            query_records.append(
                {"name": name, "query": query, "status": "skipped", "reason": "empty result", "response": payload}
            )
            continue
        csv_rows.extend(rows)
        query_records.append({"name": name, "query": query, "status": "success", "response": payload})

    relative_directory = Path("metrics/prometheus")
    relative_csv = Path("metrics/prometheus/metrics.csv")
    output_directory = staging_directory / relative_directory
    csv_path = staging_directory / relative_csv

    try:
        output_directory.mkdir(parents=True, exist_ok=True)
        for record in query_records:
            document = {
                "schema_version": "1.0",
                "instance": config.instance,
                "requested_time_range": {
                    "start": time_range.start.isoformat(),
                    "end": time_range.end.isoformat(),
                    "step_seconds": config.step_seconds,
                    "rate_interval": config.rate_interval,
                },
                "queries": [record],
            }
            json_path = output_directory / f"{record['name']}.json"
            json_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=["metric", "timestamp", "value", "labels"])
            writer.writeheader()
            writer.writerows(csv_rows)
    except OSError as exc:
        for path in output_directory.glob("*.json"):
            path.unlink(missing_ok=True)
        csv_path.unlink(missing_ok=True)
        return CollectionResult("prometheus-node-exporter", "failed", reason=str(exc))

    statuses = [record["status"] for record in query_records]
    failed_count = statuses.count("failed")
    skipped_count = statuses.count("skipped")
    successful_count = statuses.count("success")
    if successful_count == len(statuses):
        status, reason = "success", None
    elif successful_count:
        status = "partial"
        reason = f"{successful_count} succeeded, {failed_count} failed, {skipped_count} empty"
    elif failed_count:
        status, reason = "failed", f"all queries unavailable; {failed_count} failed"
    else:
        status, reason = "skipped", "all queries returned empty results"
    return CollectionResult(
        "prometheus-node-exporter",
        status,
        output=relative_directory.as_posix(),
        reason=reason,
    )
