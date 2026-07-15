from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from incident_collector.collectors.system import collect_system_summary
from incident_collector.os_detection import OSInfo


def test_collects_summary_and_limits_process_rows(tmp_path: Path) -> None:
    commands = []
    process_output = "PID PPID COMMAND %CPU %MEM\n" + "\n".join(
        f"{number} 1 process-{number} {number}.0 1.0" for number in range(1, 25)
    )

    def fake_runner(command, **kwargs):
        commands.append((command, kwargs))
        stdout = process_output if command[0] == "ps" else f"{command[0]} output\n"
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    result = collect_system_summary(
        OSInfo("ubuntu", "24.04", "Ubuntu 24.04 LTS"),
        tmp_path,
        runner=fake_runner,
        process_limit=15,
        collected_at=datetime.fromisoformat("2026-07-15T12:00:00+09:00"),
    )

    summary = (tmp_path / "metadata/system-summary.txt").read_text(encoding="utf-8")
    assert result.status == "success"
    assert "2026-07-15T12:00:00+09:00" in summary
    assert "process-15" in summary
    assert "process-16" not in summary
    assert all(isinstance(command, list) for command, _ in commands)
    assert all("shell" not in kwargs for _, kwargs in commands)


def test_preserves_summary_when_one_command_fails(tmp_path: Path) -> None:
    def fake_runner(command, **kwargs):
        if command[0] == "lscpu":
            return SimpleNamespace(returncode=1, stdout="", stderr="not available")
        return SimpleNamespace(returncode=0, stdout=f"{command[0]} output\n", stderr="")

    result = collect_system_summary(
        OSInfo("ubuntu", "24.04", "Ubuntu 24.04 LTS"),
        tmp_path,
        runner=fake_runner,
    )

    summary = (tmp_path / "metadata/system-summary.txt").read_text(encoding="utf-8")
    assert result.status == "partial"
    assert result.output == "metadata/system-summary.txt"
    assert "## CPU\nUnavailable: not available" in summary
    assert "## Memory\nfree output" in summary
