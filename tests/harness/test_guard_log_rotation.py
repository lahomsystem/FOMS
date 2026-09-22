"""SHELL_GUARD_LOG 캡·월별 보관 계약 (ablation v2 §5, 2026-09-10).

300행 캡은 관측창이 사흘뿐이라 가드 실효를 판정할 수 없었다(원장 §3). 캡을 3,000행으로
올리고, 밀려난 행은 행의 월별 보관 파일로 옮겨 잃지 않는다. Claude·Cursor 훅 2종은
같은 writer(`tools/harness/guard_log.py`)를 쓴다 — 캡을 두 곳에서 따로 관리하지 않는다.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_guard_log():
    """tools/harness/guard_log.py 를 저장소 경로에서 직접 로드한다."""
    module_path = REPO_ROOT / "tools" / "harness" / "guard_log.py"
    spec = importlib.util.spec_from_file_location("guard_log_under_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_rows(n: int, month: str = "2026-08") -> list[str]:
    """`month` 안의 시각으로 n 개 행을 만든다(캡 시험용)."""
    return [
        f"| {month}-01 {i // 3600:02d}:{(i // 60) % 60:02d}:{i % 60:02d} | ask | `x` | `cmd{i}` |\n"
        for i in range(n)
    ]


def test_cap_is_3000_and_trimmed_rows_go_to_monthly_archive(tmp_path: Path) -> None:
    """3,000행을 넘기면 가장 오래된 행이 본 파일에서 빠지고 그 달 보관 파일에 append 된다."""
    gl = _load_guard_log()
    assert gl.LOG_CAP == 3000
    log = tmp_path / "SHELL_GUARD_LOG.md"
    log.write_text("\n".join(gl.LOG_HEADER) + "\n" + "".join(_seed_rows(3000)), encoding="utf-8")

    gl.append_guard_row(str(tmp_path), "ask", "라벨", "git push origin deploy")

    kept = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.startswith("| 20")]
    assert len(kept) == 3000
    assert "`cmd0`" not in kept[0], "가장 오래된 행이 본 파일에 남아 있다"
    assert kept[-1].endswith("`git push origin deploy` |")
    archive = tmp_path / "SHELL_GUARD_LOG.archive-2026-08.md"
    assert archive.exists(), "밀려난 행의 월별 보관 파일이 없다"
    assert "`cmd0`" in archive.read_text(encoding="utf-8")


def test_append_creates_file_with_header_when_missing(tmp_path: Path) -> None:
    """로그 파일이 없으면 헤더와 함께 만든다."""
    gl = _load_guard_log()
    gl.append_guard_row(str(tmp_path / "nested"), "deny", "라벨", "cmd")
    text = (tmp_path / "nested" / "SHELL_GUARD_LOG.md").read_text(encoding="utf-8")
    assert text.startswith("# Shell Guard Log")
    assert text.rstrip().endswith("`cmd` |")


def test_resolve_log_dir_prefers_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """FOMS_HARNESS_LOG_DIR 가 있으면 그 경로, 없으면 <project_root>/docs/harness/logs."""
    gl = _load_guard_log()
    monkeypatch.setenv("FOMS_HARNESS_LOG_DIR", str(tmp_path / "env"))
    assert Path(gl.resolve_log_dir("C:/x")) == tmp_path / "env"
    monkeypatch.delenv("FOMS_HARNESS_LOG_DIR")
    assert Path(gl.resolve_log_dir("C:/x")) == Path("C:/x/docs/harness/logs")


def test_claude_and_cursor_hooks_share_the_writer() -> None:
    """두 훅 모두 공용 writer 를 쓰고 자체 캡 상수를 갖지 않는다."""
    for rel in (".claude/hooks/guard_shell.py", ".cursor/hooks/guard_shell.py"):
        src = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "append_guard_row" in src, rel
        assert "_LOG_CAP" not in src, f"{rel} 가 자체 캡을 갖는다"
