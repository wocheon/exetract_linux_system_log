"""Ubuntu 24.04 detection based on /etc/os-release."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class UnsupportedOSError(RuntimeError):
    """Raised when the current OS is outside the MVP support target."""


@dataclass(frozen=True)
class OSInfo:
    identifier: str
    version_id: str
    pretty_name: str


def detect_ubuntu(path: Path = Path("/etc/os-release")) -> OSInfo:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise UnsupportedOSError(f"unable to read {path}: {exc}") from exc

    values = {}
    for line in lines:
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value.strip().strip("\"'")

    identifier = values.get("ID", "")
    version_id = values.get("VERSION_ID", "")
    if identifier != "ubuntu" or version_id != "24.04":
        detected = values.get("PRETTY_NAME", f"{identifier} {version_id}").strip()
        raise UnsupportedOSError(f"MVP supports Ubuntu 24.04 LTS only; detected: {detected or 'unknown'}")
    return OSInfo(identifier, version_id, values.get("PRETTY_NAME", "Ubuntu 24.04 LTS"))

