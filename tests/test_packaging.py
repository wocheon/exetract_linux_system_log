from __future__ import annotations

import hashlib
import tarfile
from datetime import datetime
from pathlib import Path

from incident_collector.config import TimeRange
from incident_collector.output import create_archive


def test_creates_tar_gz_and_sha256(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "manifest.json").write_text("{}\n", encoding="utf-8")
    time_range = TimeRange(
        datetime.fromisoformat("2026-07-15T10:00:00+09:00"),
        datetime.fromisoformat("2026-07-15T11:00:00+09:00"),
        "Asia/Seoul",
    )

    archive, checksum = create_archive(staging, tmp_path / "output", "TARGET_001", time_range)

    assert archive.exists()
    assert checksum is not None and checksum.exists()
    expected = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert checksum.read_text(encoding="ascii").split()[0] == expected
    with tarfile.open(archive, "r:gz") as tar:
        assert any(name.endswith("/manifest.json") for name in tar.getnames())
