"""EDIT_LOG Session 컬럼 계약 테스트.

커버:
  - append_edit_row 4컬럼 기록 / 구세대 3컬럼 행 혼재 시 기존 소비자 파싱 무손상
  - dedup: 같은 파일·같은 세션은 skip 유지, 같은 파일·다른 세션은 기록
  - track_edits 세션 태그: 미상 id 는 "-"
  - track_edits main 은 EDIT_LOG 만 쓰고 additionalContext 를 주입하지 않는다
    (동시편집 경고는 2026-09-10 ablation v2 로 제거 — 원장 H-28·H-29)

모든 파일 I/O는 tmp_path 안에서만 일어난다(실 EDIT_LOG 불가침).
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

NOW = datetime(2026, 7, 29, 12, 0, 0)
LEGACY_HEADER = "# Edit Log\n\n| Time | File | Tool |\n|------|------|------|\n"

# hook_log_utils를 sys.path 오염 없이 격리 로드 (고유 모듈명 사용).
_HLU_PATH = REPO_ROOT / "tools" / "harness" / "hook_log_utils.py"
_spec = importlib.util.spec_from_file_location("hook_log_utils_editlog_test", _HLU_PATH)
assert _spec is not None and _spec.loader is not None
hlu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hlu)


def _load_hook(module_name: str, relative_path: str = ".claude/hooks/track_edits.py"):
    """`.claude/hooks/*` 모듈을 fresh 로드하고 sys.path/shared_utils를 복원한다."""
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
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


def _row(minutes_ago: int, rel_path: str, session: str | None = None, tool: str = "Edit") -> str:
    """NOW 기준 `minutes_ago`분 전 EDIT_LOG 행(session=None이면 구세대 3컬럼)."""
    stamp = (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%d %H:%M:%S")
    if session is None:
        return f"| {stamp} | `{rel_path}` | {tool} |\n"
    return f"| {stamp} | `{rel_path}` | {tool} | {session} |\n"


def _write_log(tmp_path: Path, rows: list[str], *, legacy_header: bool = False) -> Path:
    """헤더 + 주어진 행으로 EDIT_LOG를 만들고 경로를 반환한다."""
    path = tmp_path / "EDIT_LOG.md"
    header = LEGACY_HEADER if legacy_header else "\n".join(hlu.EDIT_LOG_HEADER_LINES) + "\n"
    path.write_text(header + "".join(rows), encoding="utf-8")
    return path


# --- 1. 4컬럼 기록 · 구세대 행 혼재 시 소비자 무손상 -----------------------
def test_append_adds_session_column_and_keeps_consumers_intact(tmp_path: Path) -> None:
    """새 행은 4컬럼, 구세대 3컬럼 행과 혼재해도 기존 파서가 그대로 동작한다."""
    log = _write_log(tmp_path, [_row(5, "legacy/old.py")], legacy_header=True)
    stamp = (NOW - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")

    assert hlu.append_edit_row(
        str(log), "apps/api/new.py", "Edit", timestamp=stamp, session="s2bbbbbb"
    ) is True

    content = log.read_text(encoding="utf-8")
    assert "| Time | File | Tool | Session |" in content, "헤더에 Session 컬럼이 없다"
    assert f"| {stamp} | `apps/api/new.py` | Edit | s2bbbbbb |" in content
    # cols[0]/cols[1]만 쓰는 기존 소비자(guard_shell·quality_check 계열) 무손상
    assert hlu.read_recent_edited_files(str(log)) == ["apps/api/new.py", "legacy/old.py"]


# --- 2. dedup: 세션이 다르면 기록돼야 감지가 가능하다 ----------------------
def test_dedup_skips_same_session_but_records_other_session(tmp_path: Path) -> None:
    """같은 파일 300초 내: 같은 세션은 skip, 다른 세션은 기록(감지 전제 조건)."""
    log = tmp_path / "EDIT_LOG.md"

    assert hlu.append_edit_row(str(log), "app.py", "Edit", session="s1aaaaaa") is True
    assert hlu.append_edit_row(str(log), "app.py", "Edit", session="s1aaaaaa") is False
    assert hlu.append_edit_row(str(log), "app.py", "Edit", session="s2bbbbbb") is True

    rows = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.startswith("| 20")]
    assert len(rows) == 2, f"세션별 1행씩 남아야 한다: {rows}"


def test_dedup_treats_legacy_row_as_dash_session(tmp_path: Path) -> None:
    """세션 컬럼 없는 구세대 행은 "-" 세션으로 간주해 기본 호출과 dedup된다."""
    log = tmp_path / "EDIT_LOG.md"
    log.write_text(
        "\n".join(hlu.EDIT_LOG_HEADER_LINES) + "\n" + f"| {hlu._now()} | `app.py` | Cursor |\n",
        encoding="utf-8",
    )

    assert hlu.append_edit_row(str(log), "app.py", "Edit") is False


def test_session_tag_maps_missing_id_to_dash() -> None:
    """session_id 부재/unknown은 "-"(미상)으로 기록해 타 세션 오탐을 막는다."""
    module = _load_hook("track_edits_tag")

    assert module._session_tag({}) == "-"
    assert module._session_tag({"session_id": "unknown"}) == "-"
    assert module._session_tag({"session_id": "abcdef0123456789"}) == "abcdef01"



# --- PostToolUse: EDIT_LOG 기록만, 주입 없음 ------------------------------
def test_hook_main_records_edit_log_without_injection(tmp_path: Path, monkeypatch, capsys) -> None:
    """타 세션 편집이 EDIT_LOG 에 있어도 훅 main 은 행만 추가하고 stdout 에 아무것도 내지 않는다."""
    module = _load_hook("track_edits_stdout")
    proj = tmp_path / "proj"
    runtime = proj / "docs" / "harness" / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    target = proj / "apps" / "api" / "orders.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x = 1", encoding="utf-8")
    stamp = hlu._now()
    (runtime / "EDIT_LOG.md").write_text(
        "\n".join(hlu.EDIT_LOG_HEADER_LINES)
        + "\n"
        + f"| {stamp} | `apps/api/orders.py` | Edit | s2bbbbbb |\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "get_project_root", lambda: str(proj))
    monkeypatch.setattr(module, "harness_runtime_path", lambda *p: str(runtime.joinpath(*p)))
    monkeypatch.setattr(
        module,
        "read_stdin_json",
        lambda: {
            "tool_name": "Edit",
            "session_id": "s1aaaaaa-full-id",
            "tool_input": {"file_path": str(target)},
        },
    )

    module.main()

    assert capsys.readouterr().out == "", "동시편집 경고 주입은 제거됐다"
    content = (runtime / "EDIT_LOG.md").read_text(encoding="utf-8")
    assert "| s1aaaaaa |" in content, "자기 세션 편집 행이 기록돼야 한다"
    assert not (runtime / "concurrent_notice_state.json").exists()
    pending = runtime / ".claude_pending_verify.json"
    assert pending.exists() and "apps/api/orders.py" in pending.read_text(encoding="utf-8")
