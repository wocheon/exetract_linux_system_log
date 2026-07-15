from __future__ import annotations

from pathlib import Path

from incident_collector.collectors.files import collect_files


def test_copies_regular_file_without_using_real_var_log(tmp_path: Path) -> None:
    source = tmp_path / "source.log"
    source.write_text("sample log\n", encoding="utf-8")
    staging = tmp_path / "staging"

    result = collect_files((str(source.absolute()),), staging)[0]

    assert result.status == "success"
    assert result.output is not None
    assert (staging / result.output).read_text(encoding="utf-8") == "sample log\n"


def test_missing_file_is_skipped(tmp_path: Path) -> None:
    result = collect_files((str((tmp_path / "missing.log").absolute()),), tmp_path / "staging")[0]

    assert result.status == "skipped"
    assert result.reason == "file not found"


def test_relative_source_is_rejected(tmp_path: Path) -> None:
    result = collect_files(("relative.log",), tmp_path / "staging")[0]

    assert result.status == "failed"
    assert "absolute" in (result.reason or "")


def test_symbolic_link_is_rejected(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.log"
    source.write_text("sample", encoding="utf-8")
    original_is_symlink = Path.is_symlink

    def fake_is_symlink(path: Path) -> bool:
        return path == source or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    result = collect_files((str(source.absolute()),), tmp_path / "staging")[0]

    assert result.status == "failed"
    assert "symbolic" in (result.reason or "")
