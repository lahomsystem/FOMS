"""`.claude/hooks/session_start.py` 동시 편집 감지(`_concurrent_edit_note`) 계약 테스트.

커버:
  - 윈도우 내 코드 편집 → [CONCURRENT-EDIT] 권고 + basename 노출
  - 윈도우 밖 편집만 / 문서 편집만 / compact source → 무주입
  - 깨진 행·파일 부재 → 크래시 없이 빈 문자열(fail-open)
  - env FOMS_CONCURRENT_EDIT_WINDOW_MIN 윈도우 override

실파일(EDIT_LOG.md·SESSION_LOG.md)은 건드리지 않고 tmp 경로만 주입한다.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_REL = ".claude/hooks/session_start.py"

NOW = datetime(2026, 7, 29, 12, 0, 0)


def _load_hook(module_name: str):
    """session_start 훅 모듈을 fresh 로드하고 sys.path/shared_utils를 복원한다."""
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / HOOK_REL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    saved_path = list(sys.path)
    saved_shared = sys.modules.get("shared_utils")
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved_path
        if saved_shared is not None:
            sys.modules["shared_utils"] = saved_shared
        else:
            sys.modules.pop("shared_utils", None)
    return module


def _edit_log(tmp_path: Path, rows: list[str]) -> str:
    """헤더 + 주어진 본문 행으로 가짜 EDIT_LOG를 만들고 경로를 반환한다."""
    path = tmp_path / "EDIT_LOG.md"
    header = "# Edit Log\n\n| Time | File | Tool |\n|------|------|------|\n"
    path.write_text(header + "".join(rows), encoding="utf-8")
    return str(path)


def _row(minutes_ago: int, rel_path: str) -> str:
    """NOW 기준 `minutes_ago`분 전 편집 행을 만든다."""
    stamp = (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%d %H:%M:%S")
    return f"| {stamp} | `{rel_path}` | Edit |\n"


def _note(module, tmp_path: Path, rows: list[str], source: str = "startup") -> str:
    """가짜 EDIT_LOG를 주입해 `_concurrent_edit_note`를 호출한다."""
    return module._concurrent_edit_note(
        source, edit_log_path=_edit_log(tmp_path, rows), now=NOW
    )


def test_in_window_code_edit_injects_note(tmp_path: Path) -> None:
    """윈도우 내 .py 편집 1건이면 권고문과 파일 basename이 실린다."""
    module = _load_hook("session_start_in_window")

    note = _note(module, tmp_path, [_row(5, "apps/api/orders.py")])

    assert "[CONCURRENT-EDIT]" in note
    assert "orders.py" in note
    assert "session_worktree.py create" in note
    assert note.startswith("\n"), "이어붙이기 안전을 위해 개행으로 시작해야 한다"


def test_out_of_window_edits_are_ignored(tmp_path: Path) -> None:
    """윈도우(30분) 밖 편집만 있으면 아무것도 주입하지 않는다."""
    module = _load_hook("session_start_out_of_window")

    assert _note(module, tmp_path, [_row(120, "apps/api/orders.py")]) == ""


def test_doc_only_edits_are_ignored(tmp_path: Path) -> None:
    """.md·.txt·docs/ 편집만이면 코드 편집이 아니므로 무주입."""
    module = _load_hook("session_start_docs_only")

    rows = [
        _row(1, "docs/AI_STATUS.md"),
        _row(2, "docs/harness/runtime/EDIT_LOG.md"),
        _row(3, "notes.txt"),
        _row(4, "README.md"),
    ]
    assert _note(module, tmp_path, rows) == ""


def test_compact_source_skips_detection(tmp_path: Path) -> None:
    """compact 재개는 자기 세션 편집이 남아 있어 오탐 — 무주입."""
    module = _load_hook("session_start_compact")

    assert _note(module, tmp_path, [_row(1, "app.py")], source="compact") == ""


def test_broken_rows_do_not_break_detection(tmp_path: Path) -> None:
    """깨진 행이 섞여도 크래시 없이 정상 판정한다."""
    module = _load_hook("session_start_broken_rows")

    rows = [
        "| not-a-timestamp | `app.py` | Edit |\n",
        "쓰레기 행\n",
        "| 2026-13-45 99:99:99 | `app.py` | Edit |\n",
        _row(3, "services/pricing.py"),
    ]
    note = _note(module, tmp_path, rows)

    assert "[CONCURRENT-EDIT]" in note
    assert "1건" in note
    assert "pricing.py" in note


def test_missing_edit_log_returns_empty(tmp_path: Path) -> None:
    """EDIT_LOG 파일 부재는 정상(신규 환경) — 빈 문자열."""
    module = _load_hook("session_start_missing_log")

    note = module._concurrent_edit_note(
        "startup", edit_log_path=str(tmp_path / "nope" / "EDIT_LOG.md"), now=NOW
    )
    assert note == ""


def test_window_env_override(tmp_path: Path, monkeypatch) -> None:
    """FOMS_CONCURRENT_EDIT_WINDOW_MIN=5면 5분 밖 편집은 감지하지 않는다."""
    module = _load_hook("session_start_env_window")
    monkeypatch.setenv("FOMS_CONCURRENT_EDIT_WINDOW_MIN", "5")

    inside = _note(module, tmp_path, [_row(3, "app.py")])
    outside = _note(module, tmp_path, [_row(20, "app.py")])

    assert "최근 5분 내" in inside
    assert outside == ""


def test_invalid_window_env_falls_back(tmp_path: Path, monkeypatch) -> None:
    """윈도우 env가 정수가 아니면 기본 30분으로 폴백하고 로그를 남긴다."""
    module = _load_hook("session_start_bad_env")
    monkeypatch.setenv("FOMS_CONCURRENT_EDIT_WINDOW_MIN", "abc")
    logged: list[str] = []
    monkeypatch.setattr(module, "hook_log", lambda msg, tag="hook": logged.append(msg))

    note = _note(module, tmp_path, [_row(10, "app.py")])

    assert "최근 30분 내" in note
    assert logged, "잘못된 env 값은 fail-open이라도 로그를 남겨야 한다"
