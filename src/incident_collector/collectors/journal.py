"""Read-only systemd journal collector."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from ..config import TimeRange
from ..output import CollectionResult


Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def build_journal_command(time_range: TimeRange) -> list[str]:
    return [
        "journalctl",
        "--since",
        time_range.start.isoformat(),
        "--until",
        time_range.end.isoformat(),
        "--no-pager",
        "--output=short-iso-precise",
    ]


def collect_journal(
    time_range: TimeRange,
    staging_directory: Path,
    runner: Runner = subprocess.run,
) -> CollectionResult:
    relative_output = Path("logs/journal/system.log")
    destination = staging_directory / relative_output
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = build_journal_command(time_range)

    try:
        with destination.open("wb") as output_file:
            completed = runner(
                command,
                stdout=output_file,
                stderr=subprocess.PIPE,
                check=False,
                timeout=120,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        destination.unlink(missing_ok=True)
        return CollectionResult(name="journal-system", status="failed", reason=str(exc))

    if completed.returncode != 0:
        destination.unlink(missing_ok=True)
        stderr = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
        reason = stderr[:500] or f"journalctl exited with status {completed.returncode}"
        return CollectionResult(name="journal-system", status="failed", reason=reason)

    return CollectionResult(name="journal-system", status="success", output=relative_output.as_posix())
