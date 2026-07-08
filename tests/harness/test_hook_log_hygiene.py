"""런타임 로그 위생 회귀 테스트 (Phase 0-4 로그 계층 수술).

커버:
  - SESSION_LOG 로테이션: 25세션 → 최신 20블록만, 최신이 맨 위 (역전 버그 회귀 방지)
  - session_stop: 자기 블록 필드 갱신 (새 블록/행 append 아님)
  - track_edits: 트리밖 편집은 EDIT_LOG·pending_verify 모두 미기록 (commonpath 판정)
  - track_edits: 트리 안 .py는 EDIT_LOG·pending_verify 모두 기록
  - EDIT_LOG 50행 캡
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# hook_log_utils를 sys.path 오염 없이 격리 로드 (고유 모듈명 사용).
_HLU_PATH = REPO_ROOT / "tools" / "harness" / "hook_log_utils.py"
_spec = importlib.util.spec_from_file_location("hook_log_utils_hygiene_test", _HLU_PATH)
assert _spec is not None and _spec.loader is not None
hlu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hlu)


def _load_hook(module_name: str, relative_path: str):
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


# --- SESSION_LOG 로테이션 --------------------------------------------------
def test_session_rotation_keeps_newest_20_newest_first(tmp_path: Path) -> None:
    """25세션 삽입 후 최신 20블록만 남고 최신이 맨 위여야 한다(역전 버그 회귀)."""
    log = tmp_path / "SESSION_LOG.md"
    for i in range(25):
        hlu.prepend_session_block(str(log), f"sess{i:02d}", f"2026-07-08 10:{i:02d}:00")

    content = log.read_text(encoding="utf-8")
    ids = re.findall(r"### Session: (\S+)", content)

    assert len(ids) == 20, f"expected 20 blocks, got {len(ids)}"
    assert ids[0] == "sess24", "newest session must be at the top"
    assert ids[-1] == "sess05", "oldest retained session must be sess05"
    assert "sess04" not in ids, "oldest 5 sessions must be rotated out"
    assert "sess00" not in ids


def test_update_session_block_updates_not_appends(tmp_path: Path) -> None:
    """session_stop은 자기 블록 필드를 갱신하고 새 블록/행을 추가하지 않는다."""
    log = tmp_path / "SESSION_LOG.md"
    hlu.prepend_session_block(str(log), "abc12345", "2026-07-08 10:00:00")

    ok = hlu.update_session_block(
        str(log),
        "abc12345",
        {"상태": "완료", "종료": "2026-07-08 11:30:00", "편집 파일": "a.py, b.py"},
    )

    assert ok is True
    content = log.read_text(encoding="utf-8")
    assert content.count("### Session:") == 1, "must not create a second block"
    assert "- **상태**: 완료" in content
    assert "- **종료**: 2026-07-08 11:30:00" in content
    assert "- **편집 파일**: a.py, b.py" in content
    assert "- **상태**: 진행중" not in content
    assert "END" not in content, "legacy END table row must not appear"


def test_update_session_block_missing_returns_false(tmp_path: Path) -> None:
    """대상 파일이 없으면 갱신은 조용히 False."""
    log = tmp_path / "SESSION_LOG.md"
    assert hlu.update_session_block(str(log), "nope", {"상태": "완료"}) is False


# --- EDIT_LOG 캡 -----------------------------------------------------------
def test_edit_log_caps_at_50_rows_newest_kept(tmp_path: Path) -> None:
    """60개 편집 후 최신 50행만 유지된다."""
    log = tmp_path / "EDIT_LOG.md"
    for i in range(60):
        hlu.append_edit_row(
            str(log), f"foms/f{i:03d}.py", "Edit", timestamp=f"2026-07-08 10:00:{i % 60:02d}"
        )

    content = log.read_text(encoding="utf-8")
    rows = [ln for ln in content.splitlines() if ln.startswith("| 20")]
    assert len(rows) == 50, f"expected 50 rows, got {len(rows)}"
    assert "f059.py" in content, "newest must be retained"
    assert "f010.py" in content, "50th-from-newest must be retained"
    assert "f009.py" not in content, "oldest 10 must be dropped"


def test_edit_log_dedup_exact_column_not_substring(tmp_path: Path) -> None:
    """dedup은 File 컬럼 정확 비교 — `a.py`가 `aa.py`를 오탐 dedup하면 안 된다."""
    log = tmp_path / "EDIT_LOG.md"
    assert hlu.append_edit_row(str(log), "aa.py", "Edit") is True
    # 다른 파일 a.py는 substring이지만 정확 비교로 새 행이어야 한다.
    assert hlu.append_edit_row(str(log), "a.py", "Edit") is True
    content = log.read_text(encoding="utf-8")
    assert "`aa.py`" in content
    assert "`a.py`" in content


# --- track_edits 트리밖 누수 ----------------------------------------------
def _setup_proj(tmp_path: Path):
    """tmp 프로젝트 트리 + runtime 디렉터리를 만들어 반환한다."""
    proj = tmp_path / "proj"
    runtime = proj / "docs" / "harness" / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    return proj, runtime


def test_track_edits_skips_out_of_tree(tmp_path: Path, monkeypatch) -> None:
    """트리밖 .py 편집은 EDIT_LOG·pending_verify 모두 기록하지 않는다."""
    module = _load_hook("track_edits_tree_out", ".claude/hooks/track_edits.py")
    proj, runtime = _setup_proj(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    outfile = outside / "global_memory.py"
    outfile.write_text("x = 1", encoding="utf-8")

    monkeypatch.setattr(module, "get_project_root", lambda: str(proj))
    monkeypatch.setattr(module, "harness_runtime_path", lambda *p: str(runtime.joinpath(*p)))
    monkeypatch.setattr(
        module,
        "read_stdin_json",
        lambda: {
            "tool_name": "Edit",
            "session_id": "sess0001",
            "tool_input": {"file_path": str(outfile)},
        },
    )

    module.main()

    assert not (runtime / "EDIT_LOG.md").exists(), "out-of-tree edit must not touch EDIT_LOG"
    assert not (runtime / ".claude_pending_verify.json").exists(), (
        "out-of-tree .py must not pollute the Stop gate pending file"
    )


def test_track_edits_records_in_tree_py(tmp_path: Path, monkeypatch) -> None:
    """트리 안 .py 편집은 EDIT_LOG와 pending_verify 모두에 기록된다."""
    module = _load_hook("track_edits_in_tree", ".claude/hooks/track_edits.py")
    proj, runtime = _setup_proj(tmp_path)
    infile = proj / "foms" / "api" / "thing.py"
    infile.parent.mkdir(parents=True, exist_ok=True)
    infile.write_text("y = 2", encoding="utf-8")

    monkeypatch.setattr(module, "get_project_root", lambda: str(proj))
    monkeypatch.setattr(module, "harness_runtime_path", lambda *p: str(runtime.joinpath(*p)))
    monkeypatch.setattr(
        module,
        "read_stdin_json",
        lambda: {
            "tool_name": "Write",
            "session_id": "sess0001",
            "tool_input": {"file_path": str(infile)},
        },
    )

    module.main()

    edit_log = runtime / "EDIT_LOG.md"
    pending = runtime / ".claude_pending_verify.json"
    assert edit_log.exists()
    assert "foms/api/thing.py" in edit_log.read_text(encoding="utf-8")
    assert pending.exists()
    state = json.loads(pending.read_text(encoding="utf-8"))
    assert "foms/api/thing.py" in state["files"]
    assert state["session_id"] == "sess0001"
