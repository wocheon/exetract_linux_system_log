from __future__ import annotations

from pathlib import Path

import pytest

from incident_collector.os_detection import UnsupportedOSError, detect_ubuntu


def test_detects_ubuntu_2404(tmp_path: Path) -> None:
    release = tmp_path / "os-release"
    release.write_text(
        'ID=ubuntu\nVERSION_ID="24.04"\nPRETTY_NAME="Ubuntu 24.04.2 LTS"\n',
        encoding="utf-8",
    )

    info = detect_ubuntu(release)

    assert info.identifier == "ubuntu"
    assert info.version_id == "24.04"


def test_rejects_unsupported_os(tmp_path: Path) -> None:
    release = tmp_path / "os-release"
    release.write_text('ID=debian\nVERSION_ID="12"\n', encoding="utf-8")

    with pytest.raises(UnsupportedOSError, match="Ubuntu 24.04"):
        detect_ubuntu(release)
