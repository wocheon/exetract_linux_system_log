from __future__ import annotations

import json
import tarfile
from pathlib import Path

from incident_collector.cli import main
from incident_collector.os_detection import OSInfo
from incident_collector.output import CollectionResult


def test_cli_collects_temp_file_and_packages_it(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "application.log"
    source.write_text("application event\n", encoding="utf-8")
    output = tmp_path / "output"
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
target:
  os: auto
  alias: TARGET_001
collection:
  start_time: '2026-07-15T10:00:00+09:00'
  end_time: '2026-07-15T11:00:00+09:00'
  timezone: Asia/Seoul
  output_directory: '{output.as_posix()}'
  temporary_directory: '{tmp_path.as_posix()}'
  continue_on_error: true
system_logs:
  enabled: false
  collect_journal: false
log_paths:
  include:
    - '{source.as_posix()}'
output:
  archive_format: tar.gz
  include_manifest: true
  include_checksums: true
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "incident_collector.cli.detect_ubuntu",
        lambda: OSInfo("ubuntu", "24.04", "Ubuntu 24.04 LTS"),
    )

    def fake_system_summary(os_info, staging):
        destination = staging / "metadata/system-summary.txt"
        destination.parent.mkdir(parents=True)
        destination.write_text("system summary\n", encoding="utf-8")
        return CollectionResult("system-summary", "success", output="metadata/system-summary.txt")

    monkeypatch.setattr("incident_collector.cli.collect_system_summary", fake_system_summary)

    exit_code = main(["collect", "--config", str(config)])

    assert exit_code == 0
    archives = list(output.glob("*.tar.gz"))
    assert len(archives) == 1
    assert archives[0].with_suffix(archives[0].suffix + ".sha256").exists()
    with tarfile.open(archives[0], "r:gz") as tar:
        names = tar.getnames()
        manifest_name = next(name for name in names if name.endswith("/manifest.json"))
        assert any(name.endswith("/application.log") for name in names)
        assert any(name.endswith("/metadata/system-summary.txt") for name in names)
        manifest_file = tar.extractfile(manifest_name)
        assert manifest_file is not None
        manifest = json.load(manifest_file)
        statuses = {item["name"]: item["status"] for item in manifest["collections"]}
        assert statuses["system-summary"] == "success"
        assert statuses["journal-system"] == "skipped"
        assert statuses[f"file:{source.as_posix()}"] == "success"
