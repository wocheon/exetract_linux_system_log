"""Read-only snapshot of essential server information."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from ..os_detection import OSInfo
from ..output import CollectionResult


Runner = Callable[..., subprocess.CompletedProcess[str]]
PROCESS_LIMIT = 15


def _run(command: list[str], runner: Runner) -> tuple[str | None, str | None]:
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)

    if completed.returncode != 0:
        reason = (completed.stderr or "").strip()[:300]
        return None, reason or f"command exited with status {completed.returncode}"
    return (completed.stdout or "").strip(), None


def _limit_processes(output: str, limit: int) -> str:
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return "(no process information returned)"
    return "\n".join([lines[0], *lines[1 : limit + 1]])


def collect_system_summary(
    os_info: OSInfo,
    staging_directory: Path,
    runner: Runner = subprocess.run,
    *,
    process_limit: int = PROCESS_LIMIT,
    collected_at: datetime | None = None,
) -> CollectionResult:
    """Write one human-readable snapshot without exposing process arguments."""
    relative_output = Path("metadata/system-summary.txt")
    destination = staging_directory / relative_output
    sections = [
        (
            "Snapshot",
            "\n".join(
                [
                    f"Collected at: {(collected_at or datetime.now().astimezone()).isoformat()}",
                    "Note: process and resource data reflect collection time, not the requested historical range.",
                ]
            ),
        ),
        (
            "Operating System",
            f"Name: {os_info.pretty_name}\nID: {os_info.identifier}\nVersion: {os_info.version_id}",
        ),
    ]
    commands = [
        ("Kernel", ["uname", "-r"], False),
        ("CPU", ["lscpu"], False),
        ("Memory", ["free", "-h"], False),
        ("Disk Usage", ["df", "-hT"], False),
        (
            f"Top {process_limit} Processes by CPU",
            ["ps", "-eo", "pid,ppid,comm,pcpu,pmem", "--sort=-pcpu"],
            True,
        ),
        (
            f"Top {process_limit} Processes by Memory",
            ["ps", "-eo", "pid,ppid,comm,pcpu,pmem", "--sort=-pmem"],
            True,
        ),
    ]

    failed_sections: list[str] = []
    for title, command, limit_processes in commands:
        output, error = _run(command, runner)
        if error is not None:
            failed_sections.append(title)
            sections.append((title, f"Unavailable: {error}"))
        else:
            content = _limit_processes(output or "", process_limit) if limit_processes else output or "(no output)"
            sections.append((title, content))

    content = "\n\n".join(f"## {title}\n{body}" for title, body in sections) + "\n"
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    except OSError as exc:
        destination.unlink(missing_ok=True)
        return CollectionResult("system-summary", "failed", reason=str(exc))

    if failed_sections:
        return CollectionResult(
            "system-summary",
            "partial",
            output=relative_output.as_posix(),
            reason=f"unavailable sections: {', '.join(failed_sections)}",
        )
    return CollectionResult("system-summary", "success", output=relative_output.as_posix())

