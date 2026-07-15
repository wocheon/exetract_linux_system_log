from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from incident_collector.collectors.journal import build_journal_command, collect_journal
from incident_collector.config import TimeRange


def _time_range() -> TimeRange:
    return TimeRange(
        datetime.fromisoformat("2026-07-15T10:00:00+09:00"),
        datetime.fromisoformat("2026-07-15T11:00:00+09:00"),
        "Asia/Seoul",
    )


def test_builds_argument_list_without_shell() -> None:
    command = build_journal_command(_time_range())

    assert command[0] == "journalctl"
    assert "--since" in command
    assert "--until" in command


def test_collect_journal_uses_runner_without_shell(tmp_path: Path) -> None:
    captured = {}

    def fake_runner(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        kwargs["stdout"].write(b"journal line\n")
        return SimpleNamespace(returncode=0, stderr=b"")

    result = collect_journal(_time_range(), tmp_path, runner=fake_runner)

    assert result.status == "success"
    assert "shell" not in captured["kwargs"]
    assert isinstance(captured["command"], list)
    assert (tmp_path / "logs/journal/system.log").read_bytes() == b"journal line\n"


def test_records_journal_failure(tmp_path: Path) -> None:
    def fake_runner(command, **kwargs):
        return SimpleNamespace(returncode=1, stderr=b"permission denied")

    result = collect_journal(_time_range(), tmp_path, runner=fake_runner)

    assert result.status == "failed"
    assert result.reason == "permission denied"
    assert not (tmp_path / "logs/journal/system.log").exists()
